"""
Extension for strategy P20dP50dZOP.

Covers the ~20 recent days where future_gain20d is not yet realized.
Uses the same PARAMS (step, focusset_size, thresholds, No_go_GSPC_rsi) as the
regular backtest, producing partial-gain snapshots up to the latest available price.

Output: app/report/P20dP50dZOP/extension_YYYYMMDD.xlsx

Usage (from app/code/):
  python run_extension.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategies.strategy_P20dP50dZOP import build_extension

if __name__ == "__main__":
    build_extension()
