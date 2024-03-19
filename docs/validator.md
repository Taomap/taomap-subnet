# Validator 

Validators evaluate the upload speed of miners by concurrently receiving tensors of specified sizes from each miner. Each miner simultaneously transmits a tensor of a predetermined size to all validators.

# System Requirements

Validators will need high download bandwidth. 10 Gbps download speed is recommended. (1 Gbps at least)

# Getting Started

## Prerequisites

1. Clone the repo

```shell
git clone https://github.com/Taomap/taomap-subnet.git
```

2. Setup your python3 [virtual environment](https://docs.python3.org/3/library/venv.html) or [Conda environment](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#creating-an-environment-with-commands).

3. Install the requirements. From your virtual environment, run
```shell
cd taomap-subnet
pip install -e .
```

4. Login wandb with your wandb api key
```shell
wandb login
```
Please reach out to the subnet owner to access Taomap wandb project. Contact can be made either through Discord by messaging chaindude :: taomap [τ, κ] or via email at chaindude613@gmail.com. Kindly provide your Wandb email address for access authorization.

5. Make sure you've [created a Wallet](https://docs.bittensor.com/getting-started/wallets) and [registered a hotkey](https://docs.bittensor.com/subnets/register-and-participate).

6. (Optional) Run a Subtensor instance:

Your node will run better if you are connecting to a local Bittensor chain entrypoint node rather than using Opentensor's. 
We recommend running a local node as follows and passing the ```--subtensor.network local``` flag to your running miners/validators. 
To install and run a local subtensor node follow the commands below with Docker and Docker-Compose previously installed.
```bash
git clone https://github.com/opentensor/subtensor.git
cd subtensor
docker compose up --detach
```6
---

# Running the Validator

## With auto-updates

We highly recommend running the validator with auto-updates. This will help ensure your validator is always running the latest release, helping to maintain a high vtrust.

Prerequisites:
1. To run with auto-update, you will need to have [pm2](https://pm2.keymetrics.io/) installed.
2. Make sure your virtual environment is activated. This is important because the auto-updater will automatically update the package dependencies with pip.
3. Make sure you're using the main branch: `git checkout main`.

From the taomap-subnet folder:
```shell
pm2 start --name taomap-vali-updater --interpreter python3 scripts/start_validator.py -- --pm2_name taomap-vali --wallet.name coldkey --wallet.hotkey hotkey [other vali flags]
```

This will start a process called `taomap-vali-updater`. This process periodically checks for a new git commit on the current branch. When one is found, it performs a `pip install` for the latest packages, and restarts the validator process (who's name is given by the `--pm2_name` flag)

## Without auto-updates

If you'd prefer to manage your own validator updates...

From the taomap-subnet folder:
```shell
pm2 start python3 -- ./neurons/validator.py --wallet.name coldkey --wallet.hotkey hotkey
```

# Configuration

## Flags

The Validator offers some flags to customize properties, such as the device to evaluate on and the number of models to evaluate each step.

You can view the full set of flags by running
```shell
python3 ./neurons/validator.py -h
```

## Test Running Validation

Test running validation:
```shell
python3 neurons/validator.py 
    --wallet.name YOUR_WALLET_NAME
    --wallet.hotkey YOUR_WALLET_HOTKEY 
    --device YOUR_CUDA DEVICE
    --wandb.off
    --offline
```
---