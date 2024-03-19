# System Requirements

Miners will need enough network bandwidth and high network port (more than 10 Gbps), at least 20 Gb ssd (or nvme) disk space.

Prefered RAM size is 8 GB.

# Getting started

## Prerequisites

1. Clone the repo

```shell
git clone https://github.com/Taomap/taomap-subnet.git
```

3. Setup your python [virtual environment](https://docs.python.org/3/library/venv.html) or [Conda environment](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#creating-an-environment-with-commands).

4. Install the requirements. From your virtual environment, run
```shell
cd taomap-subnet
python3 -m pip install -e .
```

5. Make sure you've [created a Wallet](https://docs.bittensor.com/getting-started/wallets) and [registered a hotkey](https://docs.bittensor.com/subnets/register-and-participate).

6. (Optional) Run a Subtensor instance:

Your node will run better if you are connecting to a local Bittensor chain entrypoint node rather than using Opentensor's. 
We recommend running a local node as follows and passing the ```--subtensor.network local``` flag to your running miners/validators. 
To install and run a local subtensor node follow the commands below with Docker and Docker-Compose previously installed.
```bash
git clone https://github.com/opentensor/subtensor.git
cd subtensor
docker compose up --detach
```
---

## Starting the Miner


### With auto-updates

We highly recommend running the miner with auto-updates. This will help ensure your miner is always running the latest release, helping to maintain a high vtrust.

Prerequisites:
1. To run with auto-update, you will need to have [pm2](https://pm2.keymetrics.io/) installed.
2. Make sure your virtual environment is activated. This is important because the auto-updater will automatically update the package dependencies with pip.
3. Make sure you're using the main branch: `git checkout main`.

From the taomap-subnet folder:
```shell
pm2 start --name taomap-miner-updater --interpreter python3 scripts/start_miner.py -- --pm2_name taomap-miner --wallet.name coldkey --wallet.hotkey hotkey [other miner flags]
```

This will start a process called `taomap-miner-updater`. This process periodically checks for a new git commit on the current branch. When one is found, it performs a `pip install` for the latest packages, and restarts the miner process (who's name is given by the `--pm2_name` flag)


### Without Auto Update
To start your miner the most basic command is

```shell
python3 neurons/miner.py --wallet.name coldkey --wallet.hotkey hotkey
```

- `--wallet.name`: should be the name of the coldkey that contains the hotkey your miner is registered with.

- `--wallet.hotkey`: should be the name of the hotkey that your miner is registered with.

### Flags

The Miner offers some flags to customize properties, such as how to train the model and which hugging face repo to upload to.

You can view the full set of flags by running
```shell
python3 ./neurons/miner.py -h
```

