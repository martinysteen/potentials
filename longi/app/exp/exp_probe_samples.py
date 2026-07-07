"""
exp_probe_samples.py - Spot-check the survivor sample at regular historical
probe days for eyeballing composition drift.

Probe days: every --step-th usable daynum (default 50) walking backwards from
the newest, staying inside the post-warm-up range used in the concentration
study (oldest --warmup-days usable daynums excluded).

Per probe day, the trimmed-corner survivors (top beta3m decile x strongest
median_30d decile, lower-vola100d half) are listed with: ticker, Name, Sector2
(Stamdata), the POINT-IN-TIME win/loss label per horizon (cell-level rates over
survivor history known at the probe day: from the end of warm-up to
probe - horizon, strict <, matching the production embargo; identical for every
member of a probe by design, see report 6d/6h), beta3m, median_30d, vola100d,
RankNow (longi_rank at that day; rank 1 = best), sorted ascending on RankNow
(best rank first).

Output: app/exp/output/exp_probe_samples.csv (all probes stacked, Excel-ready)
        + printed per-probe tables.
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
from exp_sector_concentration import load_sector_map
from aux_winloss_shared import (
    TARGET_SPECS,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"
INPUT_DIR = EXP_DIR.parent / "input"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Survivor-sample probes at every N-th historical daynum.")
    parser.add_argument("--ind-a", type=str, default="beta3m")
    parser.add_argument("--ind-b", type=str, default="median_30d")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--trim-ind", type=str, default="vola100d")
    parser.add_argument("--keep-frac", type=float, default=0.5)
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--warmup-days", type=int, default=150)
    parser.add_argument("--step", type=int, default=50)
    parser.add_argument("--horizons", type=str, default="20d,50d")
    return parser.parse_args()


def load_name_map() -> Dict[str, str]:
    stamdata = pd.read_csv(INPUT_DIR / "Stamdata.csv", sep=";", decimal=",", encoding="utf-8", dtype=str)
    mapping: Dict[str, str] = {}
    for _, row in stamdata.iloc[1:].iterrows():
        ticker, name = row.iloc[0], row.iloc[2]
        if pd.notna(ticker) and pd.notna(name) and name.strip() != "":
            mapping[ticker] = name.strip()
    return mapping


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    K = int(args.bins)
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    specs = [spec for spec in TARGET_SPECS if spec.key in horizons]

    print(f"exp_probe_samples.py: survivors = top-{K} {args.ind_a} x bottom {args.ind_b}, "
          f"{args.trim_ind}-trimmed (keep lowest {args.keep_frac:.0%}); "
          f"probes every {args.step} usable daynums from newest")

    # ---- corner + trim, identical to exp_corner_trim.py ---------------------
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
    survivors = corner[corner["trim_pct"] <= float(args.keep_frac)].copy()

    # ---- probe days ----------------------------------------------------------
    usable_days = np.sort(survivors["daynum"].unique())
    post_warmup = usable_days[int(args.warmup_days):]
    first_label_day = int(post_warmup[0])
    probes = list(post_warmup[::-1][::int(args.step)])  # newest first, every step-th
    print(f"  probe daynums: {', '.join(str(int(d)) for d in probes)}")

    # ---- survivor history with realized gains, for point-in-time labels -----
    # At probe day D the label uses only survivor cells whose outcome was
    # already realized at D: daynum >= end of warm-up ({first_label_day}) AND
    # daynum < D - horizon (strict <, matching the production embargo).
    hist_by_spec: Dict[str, pd.DataFrame] = {}
    gain_frames: Dict[str, pd.DataFrame] = {}
    for spec in specs:
        gain = stack_non_null(read_indicator_matrix(PROD_OUTPUT_DIR / spec.target_file)).rename("gain")
        g = gain.reset_index()
        g.columns = ["ticker", "daynum", f"gain{spec.key}"]
        gain_frames[spec.key] = g
        hist = survivors.merge(g.rename(columns={f"gain{spec.key}": "gain"}), on=["ticker", "daynum"], how="inner")
        hist_by_spec[spec.key] = hist[hist["daynum"] >= first_label_day]

    def probe_label(spec, probe_day: int) -> Dict[str, float]:
        window = hist_by_spec[spec.key]
        window = window[window["daynum"] < probe_day - spec.horizon_days]
        if window.empty:
            return {"win": float("nan"), "loss": float("nan"), "n": 0}
        return {
            "win": (window["gain"] > spec.win_threshold).mean(),
            "loss": (window["gain"] < spec.loss_threshold).mean(),
            "n": len(window),
        }

    name_map = load_name_map()
    sector_map = load_sector_map(19)
    rank = load_indicator("rank").rename("rank_now").reset_index()
    rank.columns = ["ticker", "daynum", "rank_now"]

    out_rows: List[Dict[str, str]] = []
    for probe in probes:
        day = survivors[survivors["daynum"] == probe].merge(rank, on=["ticker", "daynum"], how="left")
        for spec in specs:  # realized outcome of each pick (NaN if not yet realized)
            day = day.merge(gain_frames[spec.key], on=["ticker", "daynum"], how="left")
        day["name"] = day["ticker"].map(name_map).fillna("")
        day["sector"] = day["ticker"].map(sector_map).fillna("na")
        day = day.sort_values("rank_now", ascending=True, na_position="last")

        label = {spec.key: probe_label(spec, int(probe)) for spec in specs}
        label_txt = "; ".join(
            f"{k}: win {v['win']:.1%} / loss {v['loss']:.1%} (n={v['n']}, "
            f"daynums {first_label_day}..{int(probe) - dict((s.key, s.horizon_days) for s in specs)[k] - 1})"
            if v["n"] else f"{k}: no realized history yet"
            for k, v in label.items())

        print(f"\n  === probe daynum {int(probe)}: {len(day)} survivors ===")
        print(f"    label as of this day - {label_txt}")
        print(f"    {'ticker':<12}{'name':<26}{'sector':<14}"
              f"{'beta3m':>8}{'med30d':>8}{args.trim_ind:>9}{'RankNow':>9}"
              + "".join(f"{'gain' + spec.key:>9}" for spec in specs))
        for _, r in day.iterrows():
            rank_txt = f"{r['rank_now']:.0f}" if pd.notna(r["rank_now"]) else "-"
            gains_txt = "".join(
                f"{r['gain' + spec.key]:>9.1f}" if pd.notna(r[f"gain{spec.key}"]) else f"{'-':>9}"
                for spec in specs)
            print(f"    {r['ticker']:<12}{r['name'][:24]:<26}{r['sector'][:12]:<14}"
                  f"{r['val_a']:>8.2f}{r['val_b']:>8.1f}{r['trim_val']:>9.2f}{rank_txt:>9}{gains_txt}")
            def lbl(key: str, field: str) -> str:
                if key not in label or not label[key]["n"]:
                    return ""
                return format_cell(label[key][field]) if field != "n" else str(label[key]["n"])

            out_rows.append({
                "probe_daynum": str(int(probe)), "ticker": r["ticker"], "name": r["name"],
                "sector2": r["sector"],
                "win20": lbl("20d", "win"), "loss20": lbl("20d", "loss"), "nhist20": lbl("20d", "n"),
                "win50": lbl("50d", "win"), "loss50": lbl("50d", "loss"), "nhist50": lbl("50d", "n"),
                "beta3m": format_cell(float(r["val_a"])),
                "median_30d": format_cell(float(r["val_b"])),
                args.trim_ind: format_cell(float(r["trim_val"])),
                "rank_now": format_cell(float(r["rank_now"])) if pd.notna(r["rank_now"]) else "",
                **{f"gain{spec.key}": format_cell(float(r[f"gain{spec.key}"]))
                   if pd.notna(r[f"gain{spec.key}"]) else "" for spec in specs},
            })
        top = day["sector"].value_counts()
        print(f"    -> top sector: {top.index[0]} {top.iloc[0]}/{len(day)} ({top.iloc[0] / len(day):.0%})")

    out_path = EXP_OUTPUT_DIR / "exp_probe_samples.csv"
    cols = ["probe_daynum", "ticker", "name", "sector2", "win20", "loss20", "nhist20",
            "win50", "loss50", "nhist50", "beta3m", "median_30d", args.trim_ind, "rank_now"] \
           + [f"gain{spec.key}" for spec in specs]
    pd.DataFrame(out_rows)[cols].to_csv(out_path, sep=";", index=False)
    print(f"\n  Written: {out_path.name} ({len(out_rows)} rows, {len(probes)} probes)")

    append_manifest("exp_probe_samples.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, f"{len(probes)} probes")
    print(f"\nSUCCESS: probe samples complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
