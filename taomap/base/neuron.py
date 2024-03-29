# The MIT License (MIT)
# Copyright © 2023 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import copy
import typing

import bittensor as bt
import traceback

from abc import ABC, abstractmethod
# Sync calls set weights and also resyncs the metagraph.
from taomap.utils.config import check_config, add_args, config
from taomap.utils.misc import ttl_get_block
from taomap import __spec_version__ as spec_version
from taomap.mock import MockSubtensor, MockMetagraph
import taomap.constants as constants
import json
import requests

class BaseNeuron(ABC):
    """
    Base class for Bittensor miners. This class is abstract and should be inherited by a subclass. It contains the core logic for all neurons; validators and miners.

    In addition to creating a wallet, subtensor, and metagraph, this class also handles the synchronization of the network state via a basic checkpointing mechanism based on epoch length.
    """

    neuron_type: str = "BaseNeuron"

    @classmethod
    def check_config(cls, config: "bt.Config"):
        check_config(cls, config)

    @classmethod
    def add_args(cls, parser):
        add_args(cls, parser)

    @classmethod
    def config(cls):
        return config(cls)

    subtensor: "bt.subtensor"
    wallet: "bt.wallet"
    metagraph: "bt.metagraph"
    spec_version: int = spec_version

    @property
    def block(self):
        return ttl_get_block(self)

    def __init__(self, config=None):
        base_config = copy.deepcopy(config or BaseNeuron.config())
        self.config = self.config()
        self.config.merge(base_config)
        self.check_config(self.config)

        self.load_configuration()

        # Set up logging with the provided configuration and directory.
        bt.logging(config=self.config, logging_dir=self.config.full_path)

        # If a gpu is required, set the device to cuda:N (e.g. cuda:0)
        self.device = self.config.neuron.device

        # Log the configuration for reference.
        bt.logging.info(self.config)

        # Build Bittensor objects
        # These are core Bittensor classes to interact with the network.
        bt.logging.info("Setting up bittensor objects.")

        # The wallet holds the cryptographic key pairs for the miner.
        if self.config.mock:
            self.wallet = bt.MockWallet(config=self.config)
            self.subtensor = MockSubtensor(
                self.config.netuid, wallet=self.wallet
            )
            self.metagraph = MockMetagraph(
                self.config.netuid, subtensor=self.subtensor
            )
        else:
            self.wallet = bt.wallet(config=self.config)
            self.subtensor = bt.subtensor(config=self.config)
            self.metagraph = self.subtensor.metagraph(self.config.netuid)
        
        self.last_synced_block = self.block

        bt.logging.info(f"Wallet: {self.wallet}")
        bt.logging.info(f"Subtensor: {self.subtensor}")
        bt.logging.info(f"Metagraph: {self.metagraph}")

        # Check if the miner is registered on the Bittensor network before proceeding further.
        self.check_registered()

        # Each miner gets a unique identity (UID) in the network for differentiation.
        self.uid = self.metagraph.hotkeys.index(
            self.wallet.hotkey.ss58_address
        )
        bt.logging.info(
            f"Running neuron on subnet: {self.config.netuid} with uid {self.uid} using network: {self.subtensor.chain_endpoint}"
        )
        self.step = 0

    @abstractmethod
    async def forward(self, synapse: bt.Synapse) -> bt.Synapse:
        ...

    @abstractmethod
    def run(self):
        ...

    def sync(self):
        """
        Wrapper for synchronizing the state of the network for the given miner or validator.
        """
        # Ensure miner or validator hotkey is still registered on the network.

        if self.should_sync_metagraph():
            self.check_registered()
            self.resync_metagraph()
            self.last_synced_block = self.block

        if self.should_set_weights():
            self.set_weights()

        # Always save state.
        if self.step > 0:
            self.save_state()

    def check_registered(self):
        # --- Check for registration.
        if not self.subtensor.is_hotkey_registered(
            netuid=self.config.netuid,
            hotkey_ss58=self.wallet.hotkey.ss58_address,
        ):
            bt.logging.error(
                f"Wallet: {self.wallet} is not registered on netuid {self.config.netuid}."
                f" Please register the hotkey using `btcli subnets register` before trying again"
            )
            exit()

    def should_sync_metagraph(self):
        """
        Check if enough epoch blocks have elapsed since the last checkpoint to sync.
        """
        return self.block - self.last_synced_block > self.config.neuron.sync_length

    def should_set_weights(self) -> bool:
        # Don't set weights on initialization.
        if self.step == 0:
            return False

        # Check if enough epoch blocks have elapsed since the last epoch.
        if self.config.neuron.disable_set_weights:
            return False

        # Define appropriate logic for when set weights.
        return (
            (self.block - self.metagraph.last_update[self.uid])
            > self.config.neuron.epoch_length
            and self.neuron_type != "MinerNeuron"
        )  # don't set weights if you're a miner

    def save_state(self):
        bt.logging.warning(
            "save_state() not implemented for this neuron. You can implement this function to save model checkpoints or other useful data."
        )

    def load_state(self):
        bt.logging.warning(
            "load_state() not implemented for this neuron. You can implement this function to load model checkpoints or other useful data."
        )

    def load_configuration(self):
        try:
            url = f"{constants.API_URL}/config/mainnet.json"
            if self.config.subtensor.network == 'test':
                url = f"{constants.API_URL}/config/testnet.json"
            response = requests.get(url)
            if response.status_code != 200:
                bt.logging.error(f"Error getting configuration: {response.text}")
                return
            config = response.json()
            constants.WANDB_PROJECT = config['WANDB_PROJECT']
            constants.ORIGIN_TERM_BLOCK = config['ORIGIN_TERM_BLOCK']
            constants.BLOCKS_PER_TERM = config['BLOCKS_PER_TERM']
            constants.BLOCKS_SHARE_SEED = config['BLOCKS_SHARE_SEED']
            constants.BLOCKS_START_BENCHMARK = config['BLOCKS_START_BENCHMARK']
            constants.BLOCKS_PER_GROUP = config['BLOCKS_PER_GROUP']
            constants.BLOCKS_SEEDHASH_START = config['BLOCKS_SEEDHASH_START']
            constants.BLOCKS_SEEDHASH_END = config['BLOCKS_SEEDHASH_END']
            constants.BENCHMARK_SHAPE = eval(config['BENCHMARK_SHAPE'])
            constants.VALIDATOR_MIN_STAKE = config['VALIDATOR_MIN_STAKE']
            
            bt.logging.success(f"Loaded configuration: {config}")
        except BaseException as e:
            bt.logging.error(f"Error loading configuration: {e}")
            bt.logging.debug(traceback.format_exc())

    
    def commit_data_mock(self, data: dict[str, any]):
        response = requests.post(f"{constants.API_URL}/testnet/commit/{self.uid}", json=data)
        if response.status_code != 200:
            bt.logging.error(f"Error committing: {response.text}")
            bt.logging.debug(response.status_code)
            return False
        return True

    def commit_data(self, data: dict[str, any]):
        # if self.config.subtensor.network == 'test':
        #     return self.commit_data_mock(data)
        commit_str = json.dumps(data)
        try:
            self.subtensor.commit(self.wallet, self.config.netuid, commit_str)
            bt.logging.info(f"Committed: {commit_str}")
            return True
        except BaseException as e:
            bt.logging.error(f"Error committing: {e}")
            bt.logging.debug(traceback.format_exc())
            return False
        
    def get_commit_data_mock(self, uid):
        response = requests.get(f"{constants.API_URL}/testnet/commit/{uid}")
        if response.status_code != 200:
            bt.logging.error(f"Error getting commitment: {response.text}")
            return None
        return response.json()
    
    def get_commit_data_from_api(self, uid):
        response = requests.get(f"{constants.API_URL}/mainnet/commit/{uid}")
        if response.status_code != 200:
            bt.logging.error(f"Error getting commitment: {response.text}")
            return None
        return response.json()

    def get_commit_data(self, uid):
        return self.get_commit_data_from_api(uid)
        try:
            metadata = bt.extrinsics.serving.get_metadata(self.subtensor, self.config.netuid, self.hotkeys[uid] )
            if metadata is None:
                return None
            last_commitment = metadata["info"]["fields"][0]
            hex_data = last_commitment[list(last_commitment.keys())[0]][2:]
            data = json.loads(bytes.fromhex(hex_data).decode())
            data['block'] = metadata['block']
            return data
        except BaseException as e:
            bt.logging.error(f"Error getting commitment: {e}")
            bt.logging.debug(traceback.format_exc())
            return None
