from pathlib import Path

__version__ = "1.10.0"

WANDB_PROJECT = "taomap"


# The root directory of this project.
ROOT_DIR = Path(__file__).parent.parent

ORIGIN_TERM_BLOCK = 0
BLOCKS_PER_TERM = 400
BLOCKS_SHARE_SEED = 10
BLOCKS_START_BENCHMARK = 20
BLOCKS_PER_GROUP = 5
BLOCKS_SEEDHASH_START = 150
BLOCKS_SEEDHASH_END = 200

BENCHMARK_SHAPE = (15, 1024, 1024)

# VALIDATOR_MIN_STAKE = 5000
VALIDATOR_MIN_STAKE = 10
