"""
Verdict: do extreme gains come from low-conformity group members?

Reads the conformity grades from analyze_conformity.py and longi_future_per{20,50}d.csv,
builds a full (ticker, daynum) panel, and buckets it by conformity decile (and,
separately, by sector-beta decile) to see whether low-conformity members produce
wider dispersion / fatter tails in forward gain — not just a different mean.
Every stat is repeated on the first vs. second half of history: a pattern that
only holds in one half is not a finding (see docs/1_group_conformity.md).

REMOVED 2026-08-07: a secondary, explicitly low-power hop-level check used to read
strategy_grp v1's DomGICS_* run*.xlsx and correlate each hop's realized gain against
its focusset's mean/min conformity. v1 was retired to _archive/ that day, and nothing
outside _archive/ may read from inside it — an archived folder has to be deletable
without breaking a thing. Its last result is banked in docs/1_group_conformity.md
(finding 3); it was corroborative only and never decided anything on its own.

Usage:
    python analyze_conformity_gains.py
"""
import argparse
import os

import numpy as np
import pandas as pd

ATTRS = ["GICS", "Sector2"]
# Forward horizons, named by the longi_future_per* suffix — the "seven-pack" literal
# trading-day ladder (1d/5d/10d/20d/50d/100d/200d) produced by
# longi/app/code/longi_future_performance.py. These replaced future_gain{20,50}d.csv on
# 2026-07-31 — first via an intermediate 1m/3m (22/66-day) naming, then the same day
# corrected to this literal 20d/50d ladder. The entry convention also changed (entry is now
# the day AFTER the signal day), so results are NOT comparable to conformity_vs_gain.csv rows
# written before 2026-07-31, even though "20d"/"50d" happen to match the old future_gain20d/
# 50d day counts numerically.
HORIZONS = ["20d", "50d"]
N_DECILES = 10


def _read_matrix(path):
    df = pd.read_csv(path, sep=";", decimal=",", index_col=0)
    df.columns = df.columns.astype(int)
    return df


def _decile_stats(panel, bucket_col, value_col="gain"):
    """Per-decile-of-bucket_col: count, central tendency, dispersion, tails."""
    ranks, bin_edges = pd.qcut(panel[bucket_col], N_DECILES, labels=False, duplicates="drop", retbins=True)
    panel = panel.assign(_decile=ranks + 1)  # 1..N, 1 = lowest conformity/lowest beta
    rows = []
    for decile, grp in panel.groupby("_decile"):
        g = grp[value_col]
        rows.append({
            "decile": int(decile),
            "n": len(g),
            "mean_gain": g.mean(),
            "median_gain": g.median(),
            "std_gain": g.std(),
            "p5_gain": g.quantile(0.05),
            "p95_gain": g.quantile(0.95),
            "pct_abs_gain_gt10": (g.abs() > 10).mean() * 100,
        })
    return pd.DataFrame(rows).sort_values("decile")


def _build_panel(attr, horizon, conf_dir, gain_dir):
    conf = _read_matrix(os.path.join(conf_dir, f"longi_conf_{attr}.csv"))
    beta = _read_matrix(os.path.join(conf_dir, f"longi_sectorbeta_{attr}.csv"))
    gain = _read_matrix(os.path.join(gain_dir, f"longi_future_per{horizon}.csv"))

    tickers = conf.index.intersection(beta.index).intersection(gain.index)
    daynums = conf.columns.intersection(beta.columns).intersection(gain.columns)
    conf = conf.loc[tickers, daynums]
    beta = beta.loc[tickers, daynums]
    gain = gain.loc[tickers, daynums]

    panel = pd.concat(
        {"conf": conf.stack(), "beta": beta.stack(), "gain": gain.stack()}, axis=1
    )
    panel.index.names = ["ticker", "daynum"]
    panel = panel.dropna(subset=["conf", "gain"])
    return panel.reset_index()


def _verdict_for(attr, horizon, panel, out_rows):
    splits = {"all": panel}
    if len(panel) > 200:
        mid = panel["daynum"].median()
        splits["first_half"] = panel[panel["daynum"] <= mid]
        splits["second_half"] = panel[panel["daynum"] > mid]

    for split_name, sub in splits.items():
        if len(sub) < N_DECILES * 5:
            continue
        for bucket_type, col in [("conformity", "conf"), ("beta", "beta")]:
            sub_valid = sub.dropna(subset=[col])
            if len(sub_valid) < N_DECILES * 5:
                continue
            stats = _decile_stats(sub_valid, col)
            stats.insert(0, "split", split_name)
            stats.insert(0, "bucket_type", bucket_type)
            stats.insert(0, "horizon", horizon)
            stats.insert(0, "attribute", attr)
            out_rows.append(stats)


def _monotonicity_note(stats_df):
    """Spearman-style check: does std_gain move monotonically with decile?"""
    if stats_df is None or len(stats_df) < 3:
        return "insufficient buckets"
    corr = stats_df["decile"].corr(stats_df["std_gain"], method="spearman")
    if pd.isna(corr):
        return "undefined"
    if corr > 0.6:
        return f"std_gain RISES with decile (rho={corr:.2f}) -> higher conformity = MORE dispersion (unexpected)"
    if corr < -0.6:
        return f"std_gain FALLS with decile (rho={corr:.2f}) -> low conformity = more dispersion, as hypothesized"
    return f"no clear monotone pattern (rho={corr:.2f})"


def run(input_dir, conf_dir, output_dir):
    input_dir = os.path.expanduser(input_dir)
    conf_dir = os.path.expanduser(conf_dir)
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    all_stats = []
    monotonicity_notes = []
    for attr in ATTRS:
        for horizon in HORIZONS:
            print(f"\n=== {attr} / {horizon} ===")
            panel = _build_panel(attr, horizon, conf_dir, input_dir)
            print(f" - panel rows: {len(panel)}")
            if panel.empty:
                continue
            _verdict_for(attr, horizon, panel, all_stats)

    if not all_stats:
        print("No panels built — check that analyze_conformity.py has been run first.")
        return

    out_df = pd.concat(all_stats, ignore_index=True)
    out_path = os.path.join(output_dir, "conformity_vs_gain.csv")
    out_df.to_csv(out_path, sep=";", decimal=",", index=False)
    print(f"\nWrote {out_path} ({len(out_df)} rows)")

    print("\n--- Monotonicity check (dispersion vs conformity decile, full history) ---")
    for attr in ATTRS:
        for horizon in HORIZONS:
            sub = out_df[
                (out_df["attribute"] == attr) & (out_df["horizon"] == horizon)
                & (out_df["split"] == "all") & (out_df["bucket_type"] == "conformity")
            ]
            note = _monotonicity_note(sub)
            print(f" {attr} / {horizon}: {note}")
            monotonicity_notes.append((attr, horizon, "all", note))

    print("\n--- Half-history consistency check (does the pattern survive a split?) ---")
    for attr in ATTRS:
        for horizon in HORIZONS:
            for split in ("first_half", "second_half"):
                sub = out_df[
                    (out_df["attribute"] == attr) & (out_df["horizon"] == horizon)
                    & (out_df["split"] == split) & (out_df["bucket_type"] == "conformity")
                ]
                note = _monotonicity_note(sub)
                print(f" {attr} / {horizon} / {split}: {note}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verdict: low-conformity group members vs. forward gain dispersion.")
    parser.add_argument("--input_dir", type=str, default="~/potentials/group_conformity/app/input",
                        help="Directory with longi_future_per{20,50}d.csv")
    parser.add_argument("--conf_dir", type=str, default="~/potentials/group_conformity/app/output",
                        help="Directory with longi_conf_*.csv / longi_sectorbeta_*.csv (analyze_conformity.py output)")
    parser.add_argument("--output_dir", type=str, default="~/potentials/group_conformity/app/output")
    args = parser.parse_args()
    run(args.input_dir, args.conf_dir, args.output_dir)
