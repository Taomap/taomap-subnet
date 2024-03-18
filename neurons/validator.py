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

# Bittensor
import bittensor as bt

# Bittensor Validator:
import taomap
from taomap.validator import forward

# import base validator class which takes care of most of the boilerplate
from taomap.base.validator import BaseValidatorNeuron
import wandb
import taomap.constants as constants
import random
from sklearn.cluster import KMeans
import numpy as np
import os
import json
import taomap.utils as utils
import traceback
import threading

from taomap.validator.reward import get_rewards

class Validator(BaseValidatorNeuron):
    """
    Your validator neuron class. You should use this class to define your validator's behavior. In particular, you should replace the forward function with your own logic.

    This class inherits from the BaseValidatorNeuron class, which in turn inherits from BaseNeuron. The BaseNeuron class takes care of routine tasks such as setting up wallet, subtensor, metagraph, logging directory, parsing config, etc. You can override any of the methods in BaseNeuron if you need to customize the behavior.

    This class provides reasonable default behavior for a validator such as keeping a moving average of the scores of the miners and using them to set weights at the end of each epoch. Additionally, the scores are reset for new hotkeys at the end of each epoch.
    """

    def __init__(self, config=None):

        self.term = 0
        
        super(Validator, self).__init__(config=config)

        self.subtensor_benchmark = bt.subtensor(config=self.config)
        
        self.init_term_variables()

        bt.logging.info(self.config)

    def init_term_variables(self):
        self.is_seedhash_commited = False
        self.is_seed_commited = False
        self.is_set_weight = False
        self.is_seed_shared = False
        if not hasattr(self, 'next_seed'):
            self.next_seed = 0
        self.seed = self.next_seed
        self.next_seed = random.randint(0, 100)
        self.voted_uid = None
        self.voted_groups = []
        self.groups = None
        self.is_uploaded_group = False
        self.benchmark_state = {}
        if hasattr(self, 'benchmark_thread') and self.benchmark_thread is not None:
            self.benchmark_thread.join(1)
        self.benchmark_thread = None
        self.benchmark_version = None
        self.benchmark_finished = False
        self.update_term_bias()

    def update_term_bias(self):
        self.block_height = self.subtensor.get_current_block()
        self.current_term = (self.block_height - constants.ORIGIN_TERM_BLOCK) // constants.BLOCKS_PER_TERM
        self.term_bias = (self.block_height - constants.ORIGIN_TERM_BLOCK) % constants.BLOCKS_PER_TERM

    async def forward(self):
        """
        Validator forward pass. Consists of:
        - Generating the query
        - Querying the miners
        - Getting the responses
        - Rewarding the miners
        - Updating the scores
        """
        try: 
            self.update_term_bias()
            bt.logging.info(f"Current block height: {self.block_height}, current term: {self.current_term}, blocks: {self.term_bias}")
            if self.current_term > self.term:
                bt.logging.info(f"New term {self.current_term}")
                self.term = self.current_term
                self.init_term_variables()

            # Commit hash of the next term seed
            if self.term_bias >= constants.BLOCKS_SEEDHASH_START and self.term_bias < constants.BLOCKS_SEEDHASH_END:
                if not self.is_seedhash_commited:
                    self.is_seedhash_commited = self.commit_data({
                        "type": "seedhash",
                        "term": self.term,
                        "seedhash": hash(str(self.next_seed)),
                        "benchmark_version": self.benchmark_version
                    })
                    bt.logging.info(f"Committed seed hash for term {self.term}")
                    self.update_term_bias()
            
            # Commit seed of the current term
            if self.term_bias < constants.BLOCKS_SHARE_SEED:
                # If groups are not uploaded, upload them
                if self.groups == None:
                    self.groups = self.cluster_miners()
                if not self.is_uploaded_group:
                    self.is_uploaded_group = self.upload_state()
                # Commit seed
                if self.is_uploaded_group and not self.is_seed_commited:
                    self.is_seed_commited = self.commit_data({
                            "type": "seed",
                            "term": self.term,
                            "seedhash": hash(str(self.seed)),
                            "seed": self.seed,
                            "grouphash": hash(str(self.groups)),
                            "version": self.is_uploaded_group
                        })
                    bt.logging.info(f"Committed seed for term {self.term}")
                self.update_term_bias()
                                
            # Get all validator's commits and groups, seeds.
            if self.term_bias >= constants.BLOCKS_SHARE_SEED and self.term_bias <= constants.BLOCKS_START_BENCHMARK:
                if self.voted_uid is None:
                    self.voted_uid, self.voted_groups = self.get_vote_result()
            
            # Benchmark
            if self.term_bias >= constants.BLOCKS_START_BENCHMARK and self.term_bias < constants.BLOCKS_SEEDHASH_START:
                if not self.benchmark_finished and ( self.benchmark_thread is None or not self.benchmark_thread.is_alive() ):
                    self.start_benchmark_thread()
                return

            return await forward(self)
        except BaseException as e:
            bt.logging.error(f"Error forwarding: {e}")
            bt.logging.debug(traceback.format_exc())

    def start_benchmark_thread(self):
        self.benchmark_thread = threading.Thread(target=self.benchmark, daemon=True)
        self.benchmark_thread.start()            

    def benchmark(self):
        bt.logging.info("Benchmarking thread started")
        benchmark_started = False
        current_term = self.current_term
        current_block = self.subtensor_benchmark.get_current_block()
        term_bias = (current_block - constants.ORIGIN_TERM_BLOCK) % constants.BLOCKS_PER_TERM
        while True:
            try:
                if current_term != self.current_term:
                    bt.logging.info(f"New term {self.current_term}, exit benchmarking ...")
                    break
                if term_bias < constants.BLOCKS_START_BENCHMARK:
                    time.sleep(1)
                    continue
                if self.voted_uid is None:
                    bt.logging.warning("No voted uid")
                    time.sleep(2)
                    break
                if not benchmark_started:
                    benchmark_started = True
                    bt.logging.info("🚀 Benchmarking started")
                current_group_id = (term_bias - constants.BLOCKS_START_BENCHMARK) // constants.BLOCKS_PER_GROUP
                if current_group_id >= len(self.voted_groups):
                    bt.logging.info("✅ Benchmarking finished")
                    self.benchmark_finished = True
                    break
                current_group = self.voted_groups[current_group_id] 
                bt.logging.info(f"Benchmarking group {current_group_id}: {current_group}")

                axons = [self.metagraph.axons[uid] for uid in current_group]
                synapse = taomap.protocol.Benchmark_Speed(shape=list(constants.BENCHMARK_SHAPE))
                benchmark_at = time.time()
                responses = self.dendrite.query(axons, synapse, timeout = min(100, max(constants.BLOCKS_PER_GROUP * 8, 50)), deserialize = True)
                for i, uid in enumerate(current_group):
                    if responses[i] is None:
                        self.benchmark_state[uid] = -1
                        continue
                    arrived_at, size = responses[i]
                    bt.logging.info(f"Response from {uid}: {(size / 1024 / 1024):.2f} MB, time: {arrived_at - benchmark_at}")
                    self.benchmark_state[uid] = arrived_at - benchmark_at
                    if 'benchmark' not in self.miner_status[uid]:
                        self.miner_status[uid]['benchmark'] = {
                            self.current_term: size / (arrived_at - benchmark_at)
                        }
                    else:
                        self.miner_status[uid]['benchmark'][self.current_term] = size / (arrived_at - benchmark_at)
                
                version = self.upload_to_wandb(f'benchmark-{self.uid}', f'benchmark-{self.current_term}', self.benchmark_state)
                self.benchmark_version = version

                # wait for the next group
                old_term_bias = term_bias
                while old_term_bias == term_bias:
                    time.sleep(1)
                    current_block = self.subtensor_benchmark.get_current_block()
                    term_bias = (current_block - constants.ORIGIN_TERM_BLOCK) % constants.BLOCKS_PER_TERM

            except BaseException as e:
                bt.logging.error(f"Error benchmarking: {e}")
                bt.logging.debug(traceback.format_exc())
                time.sleep(0.1)
        bt.logging.info("Benchmarking thread finished")
    
    def get_vote_result(self):
        # Download all commits and groups, seeds
        validator_uids = [uid for uid in self.metagraph.uids if self.metagraph.stake[uid] >= constants.VALIDATOR_MIN_STAKE]
        bt.logging.info(f"Voting on validators {validator_uids}")
        # Get all commits
        commits = []
        for uid in validator_uids:
            commit_data = self.get_commit_data(uid)
            bt.logging.info(f"Commit data {uid}: {commit_data}")
            if commit_data is None:
                continue
            if commit_data['term'] != self.term or commit_data['block'] % constants.BLOCKS_PER_TERM > constants.BLOCKS_SHARE_SEED:
                bt.logging.info(f"{uid} {commit_data} is not valid for term {self.term}")
                continue
            commits.append({
                "uid": uid,
                "term": commit_data["term"],
                "block": commit_data['block'],
                "seedhash": commit_data["seedhash"],
                "seed": commit_data["seed"],
                "grouphash": commit_data["grouphash"],
                "version": commit_data["version"],
            })
        bt.logging.info("Commits: ", commits)

        # Get all shared seeds
        for commit in commits:
            data = self.download_from_wandb(f"state-{commit['uid']}", f"{self.term }", commit['version'])
            if not data:
                commit['valid'] = False
                bt.logging.warning(f"Error getting shared seed for {commit['uid']}")
                continue
            if commit["seedhash"] != data["hash"]:
                commit['valid'] = False
                bt.logging.warning(f"Seed hash mismatch for {commit['uid']}")
                continue
            commit['valid'] = True
            commit['groups'] = data['groups']

        bt.logging.info("Commits with groups and seeds: ", commits)

        valid_commits = [commit for commit in commits if commit['valid']]

        if len(valid_commits) == 0:
            bt.logging.warning("No valid commits")
            return None, []
        # Vote for the group
        sum_of_seeds = sum(commit['seed'] for commit in valid_commits)
        voted_commit = valid_commits[sum_of_seeds % len(valid_commits)]

        bt.logging.success(f"Voted validator uid: {voted_commit['uid']}, seed sum: {sum_of_seeds}")
        bt.logging.info(f"Voted groups: {voted_commit['groups']}")

        return voted_commit['uid'], voted_commit['groups']
        
    def upload_to_wandb(self, artifact_name, filename, data):
        try:
            artifact = wandb.Artifact(artifact_name, type = 'dataset')
            file_path = self.config.neuron.full_path + f'/{filename}.json'
            with open(file_path, 'w') as f:
                json_str = json.dumps(data, indent=4)
                f.write(json_str)
            artifact.add_file(file_path)
            self.wandb_run.log_artifact(artifact)
            artifact.wait()
            bt.logging.info(f'Uploaded {filename}.json to wandb, ver: {artifact.version}')
            return artifact.version
        except Exception as e:
            bt.logging.error(f'Error saving seed info: {e}')
            bt.logging.debug(traceback.format_exc())
            return None

    def download_from_wandb(self, artifact_name, filename, version = 'latest'):
        try:
            artifact_url = f"{self.config.wandb.entity}/{constants.WANDB_PROJECT}/{artifact_name}:{version}"
            artifact = wandb.use_artifact(artifact_url)
            artifact_dir = artifact.download(self.config.neuron.full_path)
            shared_file = os.path.join(artifact_dir, f"{filename}.json")
            with open(shared_file, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            bt.logging.error(f'Error downloading wandb artifact: {e}')
            bt.logging.debug(traceback.format_exc())
            return None

    def upload_state(self):
        """
        Uploads the seed and groups to wandb
        """
        return self.upload_to_wandb(f'state-{self.uid}', f'{self.term}', {
                    "term": self.term,
                    "seed": self.seed,
                    "hash": hash(str(self.seed)),
                    "groups": self.groups,
                    "grouphash": hash(str(self.groups))
                })

    def cluster_miners(self):
        """
        This function is called by the validator every time step.

        Validator should make a benchmark order to the network.

        Miners which have similar ips will be grouped together.

        Each group has 4 miners. Maximum 64 groups are allowed.

        It is responsible for querying the network and scoring the responses.

        Args:
            self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.

        """
        def ip_to_int(ip):
            octets = [int(x) for x in ip.split('.')]
            return sum([octets[i] << (24 - 8 * i) for i in range(4)])
        
        if self.miner_status is None:
            return []
        
        miner_uids = [uid for uid in self.metagraph.uids if self.metagraph.stake[uid] < constants.VALIDATOR_MIN_STAKE and self.metagraph.axons[uid].ip != "0.0.0.0" and self.miner_status[int(uid)]['job_id'] >= 0]

        if len(miner_uids) == 0:
            return []

        ips = [self.metagraph.axons[uid].ip for uid in miner_uids]

        bt.logging.debug(f"Available miner uids: {miner_uids} {ips}")
        # Filter out any duplicate IPs
        unique_ips = set()
        filtered_miner_uids = []

        for uid in miner_uids:
            ip = self.metagraph.axons[uid].ip
            stake = self.metagraph.stake[uid]
            
            if stake < constants.VALIDATOR_MIN_STAKE and ip != "0.0.0.0" and ip not in unique_ips:
                unique_ips.add(ip)
                filtered_miner_uids.append(uid)

        # Now, filtered_miner_uids contains uids with unique IPs and ips will have those unique IPs
        ips = [self.metagraph.axons[uid].ip for uid in filtered_miner_uids]
        miner_uids = filtered_miner_uids

        numerical_ips = np.array([ip_to_int(ip) for ip in ips]).reshape(-1, 1)
        
        group_count = len(miner_uids) // 4
        # Use K-Means to cluster IPs into 64 groups
        kmeans = KMeans(n_clusters=group_count, random_state=random.randint(0, 100)).fit(numerical_ips)
        labels = kmeans.labels_

        # Group IPs based on labels
        groups = {}
        for i, label in enumerate(labels):
            if label not in groups:
                groups[label] = []
            groups[label].append(ips[i])

        # Convert groups to a list of lists (each sub-list is a group of IPs)
        groups_list = list(groups.values())

        final_groups = []
        leftovers = []

        for group in groups_list:
            if len(group) > 4:
                # Split large groups into groups of 4
                for i in range(0, len(group), 4):
                    new_group = group[i:i+4]
                    if len(new_group) == 4:
                        final_groups.append(new_group)
                    else:
                        leftovers.extend(new_group)
            elif len(group) < 4:
                leftovers.extend(group)
            else:
                final_groups.append(group)

        # Step 2: Merge leftovers to form new groups of 4, if possible
        while len(leftovers) >= 4:
            final_groups.append(leftovers[:4])
            leftovers = leftovers[4:]
        
        final_groups.append(leftovers)

        # Display the groups
        for i, group in enumerate(final_groups):
            print(f"Group {i+1}: {group}")
        uid_groups = []
        for group in final_groups:
            uid_group = []
            for ip in group:
                uid_group.append(int(miner_uids[ips.index(ip)]))
            uid_groups.append(uid_group)
        random.shuffle(uid_groups)
        return uid_groups

    def should_set_weights(self) -> bool:
        """
        Returns True if the validator should set weights based on the current block height and the last time weights were set.
        """
        if not super().should_set_weights():
            return False
        if self.is_set_weight:
            return False
        if self.term_bias >= constants.BLOCKS_SEEDHASH_END:
            return super().should_set_weights()
        return False
    
    def set_weights(self):
        
        bt.logging.info(f"Analyzing benchmarks for term-{self.term}")
        # Get other validator's commits.
        commits = []
        validator_uids = [int(uid) for uid in self.metagraph.uids if self.metagraph.stake[uid] >= constants.VALIDATOR_MIN_STAKE]
        for uid in validator_uids:
            commit_data = self.get_commit_data(uid)
            if commit_data is None:
                continue
            commit_term_bias = commit_data['block'] % constants.BLOCKS_PER_TERM
            if commit_data['term'] != self.term or not (commit_term_bias >= constants.BLOCKS_SEEDHASH_START and commit_term_bias < constants.BLOCKS_SEEDHASH_END):
                continue
            commit_data['uid'] = uid
            commits.append(commit_data)
        bt.logging.info(f"Commits: {commits}")

        # Download from wandb
        for commit in commits:
            if 'benchmark_version' not in commit:
                continue
            data = self.download_from_wandb(f"benchmark-{commit['uid']}", f"benchmark-{self.term}", commit['benchmark_version'])
            if data is None:
                continue
            commit['benchmark'] = data
        
        # Filter out commits without benchmarks
        commits = [commit for commit in commits if 'benchmark' in commit]

        responses = []
        miner_uids = []
        for i in range(256):
            response = []
            for commit in commits:
                if i in commit['benchmark']:
                    response.append(commit['benchmark'][i])
            if len(response) > 0:
                responses.append(response)
                miner_uids.append(i)

        # Adjust the scores based on responses from miners.
        rewards = get_rewards(self, query=self.step, responses=responses)

        bt.logging.info(f"Scored responses: {rewards}")
        # Update the scores based on the rewards. You may want to define your own update_scores function for custom behavior.
        self.update_scores(rewards, miner_uids)
        self.is_set_weight = super().set_weights()
        
    
# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    with Validator() as validator:
        while True:
            bt.logging.info("Validator running...", time.time())
            time.sleep(24)