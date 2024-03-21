# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 ChainDude

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

import time
import typing
import bittensor as bt

# Bittensor Miner:
import taomap
import taomap.constants as constants
# import base miner class which takes care of most of the boilerplate
from taomap.base.miner import BaseMinerNeuron
import torch

class Miner(BaseMinerNeuron):
    """
    Your miner neuron class. You should use this class to define your miner's behavior. In particular, you should replace the forward function with your own logic. You may also want to override the blacklist and priority functions according to your needs.

    This class inherits from the BaseMinerNeuron class, which in turn inherits from BaseNeuron. The BaseNeuron class takes care of routine tasks such as setting up wallet, subtensor, metagraph, logging directory, parsing config, etc. You can override any of the methods in BaseNeuron if you need to customize the behavior.

    This class provides reasonable default behavior for a miner such as blacklisting unrecognized hotkeys, prioritizing requests based on stake, and forwarding requests to the forward function. If you need to define custom
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        self.benchmark_tensor = bt.Tensor.serialize(torch.zeros(*constants.BENCHMARK_SHAPE))
        self.job_id = 0

        self.axon.attach(
            forward_fn=self.forward_miner_status
        )

    async def forward(
        self, synapse: taomap.protocol.Benchmark_Speed
    ) -> taomap.protocol.Benchmark_Speed:
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        bt.logging.info(f"Benchmark request from validator-{uid} {synapse.dendrite.hotkey[:5]}")
        synapse.tensor = self.benchmark_tensor
        bt.logging.info("Returning tensor", synapse.shape)
        return synapse

    async def blacklist(
        self, synapse: taomap.protocol.Benchmark_Speed
    ) -> typing.Tuple[bool, str]:
        # TODO(developer): Define how miners should blacklist requests.
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            # Ignore requests from un-registered entities.
            bt.logging.trace(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        if self.metagraph.stake[uid] < constants.VALIDATOR_MIN_STAKE:
            # If the stake is less than the minimum stake, then we should ignore the request.
            bt.logging.trace(
                f"Blacklisting request from low-stake hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Low-stake hotkey"

        return False, "Hotkey recognized!"

    async def priority(self, synapse: taomap.protocol.Benchmark_Speed) -> float:
        # TODO(developer): Define how miners should prioritize requests.
        caller_uid = self.metagraph.hotkeys.index(
            synapse.dendrite.hotkey
        )  # Get the caller index.
        prirority = float(
            self.metagraph.S[caller_uid]
        )  # Return the stake as the priority.
        bt.logging.trace(
            f"Prioritizing {synapse.dendrite.hotkey} with value: ", prirority
        )
        return prirority

    async def forward_miner_status(self, synapse: taomap.protocol.Status) -> taomap.protocol.Status:
        try:
            caller_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
            stake = self.metagraph.stake[caller_uid]
            if stake >= constants.VALIDATOR_MIN_STAKE:
                bt.logging.info(f"Miner status request from validator-{caller_uid} {synapse.dendrite.hotkey[:5]}")
        except:
            ...
        
        synapse.version = constants.__version__
        synapse.job_id = self.job_id
        return synapse
        

# This is the main function, which runs the miner.
if __name__ == "__main__":
    with Miner() as miner:
        while True:
            bt.logging.info("Miner running...", time.time())
            time.sleep(24)