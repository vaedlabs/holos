"""Contract tests run offline: tiktoken reads its encoding from the repo, not the network."""

import os
from pathlib import Path

os.environ["TIKTOKEN_CACHE_DIR"] = str(Path(__file__).parent / "fixtures" / "tiktoken")
