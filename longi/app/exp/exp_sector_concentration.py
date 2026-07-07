"""
exp_sector_concentration.py - How sector-concentrated is the survivor sample,
over ALL history (not just today)?

Motivation: the trimmed corner (top beta3m decile x strongest median_30d decile,
lower-vola100d half kept) is currently ~one semis bet. Is that a property of the
strategy or just of this regime?

Method: rebuild the corner + trim for every usable daynum. After a warm-up
(default: the oldest 150 usable daynums are dropped), map each day's members to
Sector2 (Stamdata.csv, production column convention) and measure per day:
  top_share = count of the most frequent Sector2 / day's member count
plus number of distinct sectors and HHI (sum of squared sector shares;
1/HHI = "effective number of sectors"). Measured for BOTH segments -
the untrimmed corner and the trimmed survivors - so the trim's own effect on
concentration is visible. No outcome files involved, so the timeline extends
to the newest daynum.

Flags: --ind-a (beta3m), --ind-b (median_30d), --bins (10),
--trim-ind (vola100d), --keep-frac (0.5), --min-cells-per-day (100),
--warmup-days (150), --sector-col-index (19 = Sector2 per production).

Output: app/exp/output/exp_sector_concentration_timeline.csv
        (daynum;segment;n;n_sectors;top_sector;top_n;top_share;hhi)
        + printed summary distribution.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from exp_shared import EXP_OUTPUT_DIR, append_manifest, format_cell
from exp_joint_strata import load_indicator, within_day_bins

EXP_DIR = Path(__file__).resolve().parent
INPUT_DIR = EXP_DIR.parent / "input"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Full-history sector concentration of the corner/survivor sample.")
    parser.add_argument("--ind-a", type=str, default="beta3m")
    parser.add_argument("--ind-b", type=str, default="median_30d")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--trim-ind", type=str, default="vola100d")
    parser.add_argument("--keep-frac", type=float, default=0.5)
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--warmup-days", type=int, default=150)
    parser.add_argument("--sector-col-index", type=int, default=19)
    return parser.parse_args()


def load_sector_map(col_index: int) -> Dict[str, str]:
    """ticker -> Sector2, production convention (dtype=str, first data row is a header row)."""
    stamdata = pd.read_csv(INPUT_DIR / "Stamdata.csv", sep=";", decimal=",", encoding="utf-8", dtype=str)
    mapping: Dict[str, str] = {}
    for _, row in stamdata.iloc[1:].iterrows():
        ticker = row.iloc[0]
        sector = row.iloc[col_index]
        if pd.notna(ticker) and pd.notna(sector) and sector.strip() != "":
            mapping[ticker] = sector.strip()
    return mapping


def day_concentration(seg: pd.DataFrame) -> pd.DataFrame:
    """Per daynum: n, n_sectors, top sector name/count/share, HHI."""
    rows: List[Dict] = []
    for daynum, grp in seg.groupby("daynum"):
        counts = grp["sector"].value_counts()
        n = int(counts.sum())
        shares = counts / n
        rows.append({
            "daynum": int(daynum), "n": n, "n_sectors": int(len(counts)),
            "top_sector": counts.index[0], "top_n": int(counts.iloc[0]),
            "top_share": float(shares.iloc[0]), "hhi": float((shares ** 2).sum()),
        })
    return pd.DataFrame(rows).sort_values("daynum")


def print_summary(name: str, tl: pd.DataFrame) -> None:
    ts = tl["top_share"]
    split = float(np.median(tl["daynum"]))
    h1, h2 = tl[tl["daynum"] <= split], tl[tl["daynum"] > split]
    print(f"\n  {name} ({len(tl)} days, median members/day {tl['n'].median():.0f}):")
    print(f"    top-sector share: mean {ts.mean():.1%}  median {ts.median():.1%}  "
          f"p10 {ts.quantile(0.1):.1%}  p90 {ts.quantile(0.9):.1%}  max {ts.max():.1%}")
    print(f"    days with top share >= 1/3: {(ts >= 1 / 3).mean():.1%}   "
          f">= 50%: {(ts >= 0.5).mean():.1%}   >= 75%: {(ts >= 0.75).mean():.1%}")
    print(f"    distinct sectors/day: median {tl['n_sectors'].median():.0f}; "
          f"effective sectors (1/HHI): median {(1 / tl['hhi']).median():.1f}")
    print(f"    persistence h1 -> h2 (median top share): {h1['top_share'].median():.1%} -> {h2['top_share'].median():.1%}")
    days_on_top = tl["top_sector"].value_counts()
    top5 = ", ".join(f"{s} ({c}d, {c / len(tl):.0%})" for s, c in days_on_top.head(5).items())
    print(f"    most frequent top sector: {top5}")


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    K = int(args.bins)

    print(f"exp_sector_concentration.py: corner = top-{K} {args.ind_a} x bottom {args.ind_b}, "
          f"trim = within-corner {args.trim_ind} (keep lowest {args.keep_frac:.0%}), "
          f"warm-up = oldest {args.warmup_days} usable daynums dropped")

    # ---- rebuild corner + trim, identical to exp_corner_trim.py ------------
    a = load_indicator(args.ind_a).rename("val_a")
    b = load_indicator(args.ind_b).rename("val_b")
    ab = pd.concat([a, b], axis=1, join="inner").reset_index()
    ab.columns = ["ticker", "daynum", "val_a", "val_b"]
    sizes = ab.groupby("daynum")["val_a"].transform("size")
    ab = ab[sizes >= int(args.min_cells_per_day)].copy()
    ab["bin_a"] = within_day_bins(ab, "val_a", K)
    ab["bin_b"] = within_day_bins(ab, "val_b", K)
    corner = ab[(ab["bin_a"] == K) & (ab["bin_b"] == 1)].copy()

    trim = load_indicator(args.trim_ind).rename("trim_val").reset_index()
    trim.columns = ["ticker", "daynum", "trim_val"]
    corner = corner.merge(trim, on=["ticker", "daynum"], how="inner")
    corner["trim_pct"] = corner.groupby("daynum")["trim_val"].rank(method="first", pct=True)
    corner["kept"] = corner["trim_pct"] <= float(args.keep_frac)

    usable_days = np.sort(corner["daynum"].unique())
    if len(usable_days) <= int(args.warmup_days):
        print(f"ERROR: only {len(usable_days)} usable daynums, warm-up {args.warmup_days} leaves nothing")
        return 1
    first_day = usable_days[int(args.warmup_days)]
    corner = corner[corner["daynum"] >= first_day]
    print(f"  usable daynums: {len(usable_days)} ({usable_days[0]}..{usable_days[-1]}); "
          f"after warm-up: {corner['daynum'].nunique()} ({first_day}..{usable_days[-1]})")

    # ---- Sector2 mapping ----------------------------------------------------
    sector_map = load_sector_map(int(args.sector_col_index))
    corner["sector"] = corner["ticker"].map(sector_map).fillna("na")
    n_unmapped = int((corner["sector"] == "na").sum())
    print(f"  Sector2 mappings loaded: {len(sector_map)}; "
          f"corner rows without mapping: {n_unmapped} ({n_unmapped / len(corner):.1%}) -> 'na'")

    # ---- per-day concentration, both segments -------------------------------
    out_frames: List[pd.DataFrame] = []
    for name, seg in [("corner", corner), ("survivors", corner[corner["kept"]])]:
        tl = day_concentration(seg)
        tl.insert(1, "segment", name)
        out_frames.append(tl)
        print_summary(name, tl)

    timeline = pd.concat(out_frames, ignore_index=True)
    for col in ("top_share", "hhi"):
        timeline[col] = timeline[col].map(format_cell)
    out_path = EXP_OUTPUT_DIR / "exp_sector_concentration_timeline.csv"
    timeline.to_csv(out_path, sep=";", index=False)
    print(f"\n  Written: {out_path.name} ({len(timeline)} rows)")

    append_manifest("exp_sector_concentration.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, "full history after warm-up")
    print(f"\nSUCCESS: sector concentration timeline complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
