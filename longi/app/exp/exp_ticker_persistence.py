"""
exp_ticker_persistence.py - Are some tickers genuinely more predictable, or is
per-ticker "predictability" just noise?

Method (split-half persistence):
1. Split history at the global median daynum (same calendar split for all tickers).
2. Per ticker and half, measure the model's discriminative power as the AUC of the
   stated p_win vs the realized win event (rank-based Mann-Whitney; 0.5 = no signal).
   Same for p_loss vs the loss event.
3. Across tickers, correlate half-1 AUC with half-2 AUC (Pearson + Spearman) and
   show a quintile persistence table (tickers bucketed by half-1 AUC; mean half-2
   AUC per bucket). If early predictability does not carry into the later half,
   apparent per-ticker differences are luck.

Validity gates per (ticker, half): >= --min-obs observations and >= --min-events
of BOTH the event and the non-event class (AUC undefined otherwise).

Caveat printed with results: outcome windows overlap within a half (20/50 days),
so per-half AUCs are noisier than their n suggests; the cross-ticker persistence
correlation is the meaningful statistic here, not any single ticker's AUC.

Flags: --source (default prod), --min-obs (default 60), --min-events (default 10),
--focus-file (optional; marks those tickers in the output CSV).

Output: app/exp/output/exp_ticker_persistence_{source}.csv + printed summary.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from exp_shared import EXP_OUTPUT_DIR, append_manifest, format_cell
from exp_calibration import build_frame
from aux_winloss_shared import TARGET_SPECS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split-half persistence of per-ticker predictability.")
    parser.add_argument("--source", action="append", default=None)
    parser.add_argument("--min-obs", type=int, default=60, help="Min observations per (ticker, half).")
    parser.add_argument("--min-events", type=int, default=10,
                        help="Min events AND non-events per (ticker, half).")
    parser.add_argument("--focus-file", type=str, default=None,
                        help="Optional ticker list; marked in the output CSV.")
    args = parser.parse_args()
    if not args.source:
        args.source = ["prod"]
    return args


def auc_rank(p: np.ndarray, e: np.ndarray, min_events: int) -> float:
    """Mann-Whitney AUC of scores p against binary events e; NaN when degenerate."""
    n_pos = int(e.sum())
    n_neg = int(len(e) - n_pos)
    if n_pos < min_events or n_neg < min_events:
        return float("nan")
    r = pd.Series(p).rank(method="average").to_numpy()
    u = float(r[e == 1].sum()) - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    focus: set = set()
    if args.focus_file:
        focus = {t.strip() for t in Path(args.focus_file).read_text().splitlines() if t.strip()}

    print("exp_ticker_persistence.py: split-half persistence of per-ticker predictability")
    print(f"  Sources: {', '.join(args.source)} | gates: >= {args.min_obs} obs and "
          f">= {args.min_events} of each class per (ticker, half)")
    print("  NOTE: overlapping outcome windows make single-ticker AUCs noisy; the")
    print("  cross-ticker persistence correlation is the statistic that matters.")

    for source in args.source:
        out_rows: List[Dict[str, str]] = []
        for spec in TARGET_SPECS:
            df = build_frame(source, spec)
            if df.empty:
                print(f"  {source} {spec.key}: no scoreable cells - skipped")
                continue
            split_daynum = int(np.median(df["daynum"].unique()))
            h1 = df[df["daynum"] <= split_daynum]   # older half (daynums ascending over time)
            h2 = df[df["daynum"] > split_daynum]
            print(f"\n  {source} {spec.key}: split at daynum {split_daynum} "
                  f"(half1 n={len(h1)}, half2 n={len(h2)})")

            for prob_col, event_col, label in [("p_win", "win_event", "win"), ("p_loss", "loss_event", "loss")]:
                per_ticker: Dict[str, Dict[str, float]] = {}
                for half_name, half in [("h1", h1), ("h2", h2)]:
                    for ticker, g in half.groupby("ticker"):
                        if len(g) < int(args.min_obs):
                            continue
                        a = auc_rank(g[prob_col].to_numpy(dtype=float),
                                     g[event_col].to_numpy(dtype=int), int(args.min_events))
                        if np.isfinite(a):
                            per_ticker.setdefault(str(ticker), {})[half_name] = a
                            per_ticker[str(ticker)][f"n_{half_name}"] = len(g)

                both = {t: v for t, v in per_ticker.items() if "h1" in v and "h2" in v}
                a1 = np.array([v["h1"] for v in both.values()])
                a2 = np.array([v["h2"] for v in both.values()])
                n_t = len(both)
                if n_t >= 10:
                    pearson = float(np.corrcoef(a1, a2)[0, 1])
                    spearman = float(pd.Series(a1).corr(pd.Series(a2), method="spearman"))
                else:
                    pearson = spearman = float("nan")

                print(f"    p_{label}: {n_t} tickers valid in both halves | "
                      f"mean AUC h1={np.mean(a1):.3f} h2={np.mean(a2):.3f} | "
                      f"persistence corr: Pearson={pearson:+.3f} Spearman={spearman:+.3f}")

                if n_t >= 25:
                    q = pd.qcut(pd.Series(a1), 5, labels=False, duplicates="drop")
                    print(f"      half-1 AUC quintile -> mean half-2 AUC "
                          f"(if flat, early 'predictability' does not persist):")
                    for b in sorted(pd.Series(q).dropna().unique()):
                        mask = (q == b).to_numpy()
                        print(f"        Q{int(b) + 1}: h1={a1[mask].mean():.3f} -> h2={a2[mask].mean():.3f} "
                              f"(n={int(mask.sum())})")

                for ticker, v in sorted(both.items()):
                    out_rows.append({
                        "source": source, "horizon": spec.key, "prob": label, "ticker": ticker,
                        "focus": "1" if ticker in focus else "0",
                        "n_h1": str(int(v["n_h1"])), "n_h2": str(int(v["n_h2"])),
                        "auc_h1": format_cell(v["h1"]), "auc_h2": format_cell(v["h2"]),
                    })

        if out_rows:
            out_path = EXP_OUTPUT_DIR / f"exp_ticker_persistence_{source}.csv"
            cols = ["source", "horizon", "prob", "ticker", "focus", "n_h1", "n_h2", "auc_h1", "auc_h2"]
            pd.DataFrame(out_rows)[cols].to_csv(out_path, sep=";", index=False)
            print(f"\n  Written: {out_path.name}")

    append_manifest("exp_ticker_persistence.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, "split-half full history per source")
    print(f"\nSUCCESS: persistence analysis complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
