# =============================================================================
# run_import.py — Master import runner
# =============================================================================
# Runs all import scripts in dependency order:
#   1. cal          (no dependencies)
#   2. stocks       (no dependencies)
#   3. prices       (depends on cal + stocks)
#   4. yfinance     (depends on stocks)
#   5. longi        (depends on cal + stocks)
#   6. aux          (aux_deciles: none, aux_win_loss: cal + stocks)
#   7. longi_grp    (depends on cal)
#
# Usage:
#   python run_import.py           # run all
#   python run_import.py cal       # run one step only
#   python run_import.py cal stocks prices  # run specific steps
# =============================================================================
import sys
from pot_import_utils import log

import import_cal
import import_stocks
import import_prices
import import_yfinance
import import_longi
import import_aux
import import_longi_grp

STEPS = {
    'cal':          import_cal.run,
    'stocks':       import_stocks.run,
    'prices':       import_prices.run,
    'yfinance':     import_yfinance.run,
    'longi':        import_longi.run,
    'aux':          import_aux.run,
    'longi_grp':    import_longi_grp.run,
}

ORDER = ['cal', 'stocks', 'prices', 'yfinance', 'longi', 'aux', 'longi_grp']

def main():
    requested = sys.argv[1:] if len(sys.argv) > 1 else ORDER

    # Validate
    for step in requested:
        if step not in STEPS:
            print(f"ERROR: Unknown step '{step}'. Valid steps: {', '.join(ORDER)}")
            sys.exit(1)

    log(f"=== run_import START — steps: {', '.join(requested)} ===")

    for step in ORDER:
        if step in requested:
            log(f"--- Step: {step} ---")
            try:
                STEPS[step]()
            except Exception as e:
                log(f"ERROR in {step}: {e}")
                raise

    log("=== run_import DONE ===")

if __name__ == '__main__':
    main()
