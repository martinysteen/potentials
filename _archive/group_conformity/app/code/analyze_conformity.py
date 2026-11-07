"""
Group conformity grader (GICS / Sector2).

For each ticker and each daynum, grades how closely that ticker's daily return
tracks its own group's (GICS or Sector2) daily return — a rolling correlation,
NOT the group-relative beta longi_beta*.csv already provides (that is beta
against the market/core index, a different question). See docs/1_group_conformity.md.

Key correctness point: the group return used against a ticker excludes that
ticker itself (leave-one-out). Without this, small groups (Sector2 runs 2..74
members) would just be measuring group size, since a ticker's own weight in
its published group mean is 1/n.

Usage:
    python analyze_conformity.py
    python analyze_conformity.py --window 100 --min_periods 60
"""
import argparse
import os

import numpy as np
import pandas as pd

ATTRS = ["GICS", "Sector2"]
MIN_GROUP_OTHERS = 5  # after leave-one-out, need >=5 other members or the point is blanked
RECENT_WINDOW = 126  # ~6 trading months, for the "recent_conf" ranking column


def _read_matrix(path):
    """Longi-shaped matrix: rows=ticker, columns=daynum (as strings, newest-left)."""
    df = pd.read_csv(path, sep=";", decimal=",", index_col=0)
    df.columns = df.columns.astype(int)
    return df


def _write_matrix(df, path):
    """Restore newest-left column order and European CSV formatting."""
    df = df.reindex(sorted(df.columns, reverse=True), axis=1)
    df.to_csv(path, sep=";", decimal=",")


def _leave_one_out_group_series(returns, group_of_ticker, min_group_others):
    """
    returns: DataFrame, index=ticker, columns=daynum ascending, daily % returns.
    group_of_ticker: Series, index=ticker, value=group label (may be NaN).
    Returns (g_loo, n_others): both DataFrame shaped like `returns`.
    g_loo = leave-one-out mean daily return of the ticker's group at that daynum.
    n_others = count of other valid members in the group at that daynum.
    """
    tickers = returns.index
    groups = group_of_ticker.reindex(tickers)
    valid_group = groups.notna()

    onehot = pd.get_dummies(groups)  # (n_tickers, n_groups); all-zero row where group is NaN
    valid = returns.notna()
    r_filled = returns.fillna(0.0)

    # group_sum / group_count per (group, daynum): small matmuls (n_groups is 13 or 50)
    group_sum = onehot.T.values @ r_filled.values  # (n_groups, n_daynum)
    group_count = onehot.T.values @ valid.values.astype(float)

    # broadcast back to (n_tickers, n_daynum)
    own_group_sum = onehot.values @ group_sum
    own_group_count = onehot.values @ group_count

    own_valid = valid.values.astype(float)
    own_value = r_filled.values

    # leave-one-out: only actually remove self where the ticker's own point was valid
    loo_sum = own_group_sum - own_value * own_valid
    loo_count = own_group_count - own_valid

    with np.errstate(invalid="ignore", divide="ignore"):
        g_loo = loo_sum / loo_count
    g_loo = pd.DataFrame(g_loo, index=returns.index, columns=returns.columns)
    n_others = pd.DataFrame(loo_count, index=returns.index, columns=returns.columns)

    # blank rows for tickers with no group at all
    g_loo.loc[~valid_group, :] = np.nan
    n_others.loc[~valid_group, :] = np.nan

    return g_loo, n_others


def _write_ranking(conf, group_of_ticker, stamdata, attr, output_dir):
    """
    'Who are they' — a static per-ticker summary, sorted group-then-best-conformity-first
    (rank_within_group=1 is the highest conformity, same "small number is best" convention
    as longi_rank.csv — low-conformity members get high rank numbers).
    conf: DataFrame, index=ticker, columns=daynum ASCENDING (oldest..newest).
    Persistence (corr_t vs corr_t+250 ~ +0.6) is why a single representative grade is
    meaningful at all; recent_conf beside it shows whether a name is stable or drifting,
    without needing a full time-series column.
    """
    mean_conf = conf.mean(axis=1)
    n_valid = conf.notna().sum(axis=1)
    recent_conf = conf.iloc[:, -RECENT_WINDOW:].mean(axis=1)

    group_size = group_of_ticker.value_counts()
    name = stamdata["Name"] if "Name" in stamdata.columns else pd.Series(index=stamdata.index, dtype=object)

    ranking = pd.DataFrame({
        "group": group_of_ticker,
        "group_size": group_of_ticker.map(group_size),
        "name": name.reindex(conf.index),
        "n_valid_days": n_valid,
        "mean_conf": mean_conf,
        "recent_conf": recent_conf,
    })
    ranking = ranking.dropna(subset=["group", "mean_conf"])
    # rank=1 is BEST conformity (highest mean_conf), same convention as longi_rank.csv —
    # low-conformity members get high rank numbers.
    ranking["rank_within_group"] = ranking.groupby("group")["mean_conf"].rank(
        method="first", ascending=False
    ).astype(int)
    ranking.index.name = "ticker"
    ranking = ranking.sort_values(["group", "rank_within_group"]).reset_index()
    ranking.insert(0, "attribute", attr)

    path = os.path.join(output_dir, f"conformity_ranking_{attr}.csv")
    ranking.to_csv(path, sep=";", decimal=",", index=False)
    print(f" - wrote {path} ({len(ranking)} tickers)")
    return ranking


def _rolling_corr_and_beta(x, y, window, min_periods):
    """
    x, y: DataFrame, index=ticker, columns=daynum ascending.
    Returns (corr, beta) computed per-ticker over a trailing window on daynum.
    Uses pandas' rolling().corr()/.cov() column-wise, so operate on the
    transpose (index=daynum, columns=ticker) — each column is one ticker's
    time series, matched pairwise between x and y.
    """
    xt = x.T
    yt = y.T
    roll_x = xt.rolling(window=window, min_periods=min_periods)
    corr = roll_x.corr(yt)
    cov = roll_x.cov(yt)
    var_y = yt.rolling(window=window, min_periods=min_periods).var()
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = cov / var_y
    return corr.T, beta.T


def build_conformity(input_dir, output_dir, window, min_periods):
    input_dir = os.path.expanduser(input_dir)
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Loading longi_per1d.csv (daily returns) from {input_dir}")
    per1d = _read_matrix(os.path.join(input_dir, "longi_per1d.csv"))
    is_index_ticker = per1d.index.str.startswith("^")
    print(f" - excluding {is_index_ticker.sum()} index/benchmark tickers (^-prefixed): "
          f"{list(per1d.index[is_index_ticker])}")
    per1d = per1d.loc[~is_index_ticker]
    per1d = per1d.reindex(sorted(per1d.columns), axis=1)  # ascending for rolling math
    print(f" - shape {per1d.shape}, daynum range {per1d.columns.min()}..{per1d.columns.max()}")

    print("Loading Stamdata.csv")
    stamdata = pd.read_csv(os.path.join(input_dir, "Stamdata.csv"), sep=";", index_col=0)

    print("Loading longi_vola100d.csv (control)")
    vola = _read_matrix(os.path.join(input_dir, "longi_vola100d.csv"))
    vola = vola.reindex(sorted(vola.columns), axis=1)

    control_rows = []

    for attr in ATTRS:
        print(f"\n=== Attribute: {attr} ===")
        group_of_ticker = stamdata[attr].replace("", np.nan)

        g_loo, n_others = _leave_one_out_group_series(per1d, group_of_ticker, MIN_GROUP_OTHERS)
        print(f" - leave-one-out group series built; median n_others = {n_others.stack().median():.1f}")

        conf, beta = _rolling_corr_and_beta(per1d, g_loo, window, min_periods)

        # blank where too few other members (small Sector2 groups)
        too_small = n_others < MIN_GROUP_OTHERS
        conf = conf.mask(too_small)
        beta = beta.mask(too_small)

        conf_path = os.path.join(output_dir, f"longi_conf_{attr}.csv")
        beta_path = os.path.join(output_dir, f"longi_sectorbeta_{attr}.csv")
        _write_matrix(conf, conf_path)
        _write_matrix(beta, beta_path)
        print(f" - wrote {conf_path}")
        print(f" - wrote {beta_path}")

        _write_ranking(conf, group_of_ticker, stamdata, attr, output_dir)

        # ---- controls ----
        # 1. conformity vs volatility (must be ~0, else this is a relabeled vola grade)
        common_idx = conf.index.intersection(vola.index)
        common_cols = conf.columns.intersection(vola.columns)
        a = conf.loc[common_idx, common_cols].stack()
        b = vola.loc[common_idx, common_cols].stack()
        aligned = pd.concat([a, b], axis=1, join="inner").dropna()
        corr_vola = aligned.iloc[:, 0].corr(aligned.iloc[:, 1]) if len(aligned) > 30 else np.nan
        control_rows.append((attr, "corr(conf, vola100d)", corr_vola))

        # 2. naive vs leave-one-out group-size bias
        # naive g: self-inclusive group mean (undo the leave-one-out correction)
        own_valid = per1d.notna().values.astype(float)
        naive_num = g_loo.values * n_others.values + per1d.fillna(0.0).values * own_valid
        naive_den = n_others.values + own_valid
        with np.errstate(invalid="ignore", divide="ignore"):
            naive_g = naive_num / naive_den
        naive_g = pd.DataFrame(naive_g, index=per1d.index, columns=per1d.columns).mask(too_small)
        naive_conf, _ = _rolling_corr_and_beta(per1d, naive_g, window, min_periods)
        naive_conf = naive_conf.mask(too_small)

        group_size = group_of_ticker.value_counts()
        ticker_group_size = group_of_ticker.map(group_size)
        mean_conf_loo = conf.mean(axis=1)
        mean_conf_naive = naive_conf.mean(axis=1)
        slope_df = pd.concat([ticker_group_size, mean_conf_loo, mean_conf_naive], axis=1).dropna()
        slope_df.columns = ["group_size", "mean_conf_loo", "mean_conf_naive"]
        corr_size_loo = slope_df["group_size"].corr(slope_df["mean_conf_loo"])
        corr_size_naive = slope_df["group_size"].corr(slope_df["mean_conf_naive"])
        control_rows.append((attr, "corr(group_size, mean_conf) naive", corr_size_naive))
        control_rows.append((attr, "corr(group_size, mean_conf) leave-one-out", corr_size_loo))

        # 3. persistence: conf at t vs conf at t+~1yr (250 trading days)
        shift = 250
        if conf.shape[1] > shift:
            early = conf.iloc[:, : conf.shape[1] - shift]
            late = conf.iloc[:, shift:]
            late.columns = early.columns
            pers = pd.concat([early.stack(), late.stack()], axis=1, join="inner").dropna()
            corr_persist = pers.iloc[:, 0].corr(pers.iloc[:, 1]) if len(pers) > 30 else np.nan
        else:
            corr_persist = np.nan
        control_rows.append((attr, "persistence corr(conf_t, conf_t+250)", corr_persist))

        # 4. cross-check our reconstructed naive group mean against published longi_grp_*_per1d.csv
        grp_path = os.path.join(input_dir, f"longi_grp_{attr}_per1d.csv")
        if os.path.exists(grp_path):
            published = _read_matrix(grp_path)
            published = published.reindex(sorted(published.columns), axis=1)
            # our own reconstructed self-inclusive group mean per (group, daynum)
            onehot = pd.get_dummies(group_of_ticker.reindex(per1d.index))
            valid = per1d.notna()
            r_filled = per1d.fillna(0.0)
            group_sum = onehot.T.values @ r_filled.values
            group_count = onehot.T.values @ valid.values.astype(float)
            with np.errstate(invalid="ignore", divide="ignore"):
                recon = group_sum / group_count
            recon = pd.DataFrame(recon, index=onehot.columns, columns=per1d.columns)
            common_groups = recon.index.intersection(published.index)
            common_cols2 = recon.columns.intersection(published.columns)
            r1 = recon.loc[common_groups, common_cols2].stack()
            r2 = published.loc[common_groups, common_cols2].stack()
            check = pd.concat([r1, r2], axis=1, join="inner").dropna()
            corr_grp = check.iloc[:, 0].corr(check.iloc[:, 1]) if len(check) > 30 else np.nan
        else:
            corr_grp = np.nan
        control_rows.append((attr, f"corr(reconstructed group mean, longi_grp_{attr}_per1d)", corr_grp))

    controls_df = pd.DataFrame(control_rows, columns=["attribute", "control", "value"])
    controls_path = os.path.join(output_dir, "conformity_controls.csv")
    controls_df.to_csv(controls_path, sep=";", decimal=",", index=False)
    print(f"\nWrote controls to {controls_path}")
    print(controls_df.to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build group conformity grades (GICS / Sector2).")
    parser.add_argument("--input_dir", type=str, default="~/potentials/group_conformity/app/input")
    parser.add_argument("--output_dir", type=str, default="~/potentials/group_conformity/app/output")
    parser.add_argument("--window", type=int, default=100, help="Rolling window (trading days)")
    parser.add_argument("--min_periods", type=int, default=60, help="Minimum periods for rolling corr")
    args = parser.parse_args()
    build_conformity(args.input_dir, args.output_dir, args.window, args.min_periods)
