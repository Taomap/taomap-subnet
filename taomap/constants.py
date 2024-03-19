from pathlib import Path

__version__ = "2.0.0"

WANDB_PROJECT = "taomap"

API_URL = "https://api.taomap.ai"
# The root directory of this project.
ROOT_DIR = Path(__file__).parent.parent

ORIGIN_TERM_BLOCK = 2586000
BLOCKS_PER_TERM = 720
BLOCKS_SHARE_SEED = 20
BLOCKS_START_BENCHMARK = 40
BLOCKS_PER_GROUP = 10
BLOCKS_SEEDHASH_START = 550
BLOCKS_SEEDHASH_END = 600

BENCHMARK_SHAPE = (30, 1024, 1024)

VALIDATOR_MIN_STAKE = 5000
