# Superseded by run_extension.py (single-strategy) and future per-strategy scripts.
# This file will grow as more strategies get build_extension() wired up.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategies.strategy_P20dP50dZOP import build_extension as ext_P20dP50dZOP

if __name__ == "__main__":
    for fn in (ext_P20dP50dZOP,):
        fn()
