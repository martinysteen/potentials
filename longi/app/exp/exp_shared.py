"""
exp_shared.py - Extended fit core for the Win/Loss experimental sandbox.

One module owning everything the experimental scripts share; the ONLY place
the production fit logic is forked. Everything else (feature/target loading,
labeling, error counts) is imported read-only from aux_winloss_shared.

Lives in app/exp/ per the sandbox ground rules: production code and data are
read-only inputs; all experimental outputs go to app/exp/output/ with an
exp_ filename prefix.

Self-test: `python exp_shared.py` runs the Phase 1 acceptance checks on
synthetic data and appends a manifest line.
"""

from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Production code directory is a read-only import source.
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from aux_winloss_shared import CLASS_NAMES, CLASS_TO_INT  # noqa: E402

EXP_DIR = Path(__file__).resolve().parent
EXP_OUTPUT_DIR = EXP_DIR / "output"
MANIFEST_FILE = EXP_OUTPUT_DIR / "manifest.txt"


# ---------------------------------------------------------------------------
# Fit core (the fork)
# ---------------------------------------------------------------------------

@dataclass
class FitDiagnostics:
    """Per-fit diagnostics returned alongside predictions."""
    pipeline: Optional[Pipeline]        # fitted, or None for degenerate (single-class) fits
    train_probs: Optional[np.ndarray]   # predict_proba(x_train), expanded to full 3-class layout


def fit_predict_multinomial_ext(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    reg_lambda: float,
    max_iter: int,
    *,
    sample_weight: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, FitDiagnostics]:
    # forked from aux_winloss_shared v1 (fit_predict_multinomial), extended for experiments
    """
    Fit multinomial model and return (y_pred, probs_full, FitDiagnostics).

    Extension over production: optional per-row sample_weight (recency
    weighting) and fit diagnostics from the same single fit.

    Scaling is applied internally via StandardScaler. Callers should pass raw
    (unscaled) feature arrays. Handles missing classes in train split by
    expanding back to the full class set.
    """
    unique_classes = np.unique(y_train)
    probs_full = np.zeros((x_test.shape[0], len(CLASS_NAMES)), dtype=float)

    if unique_classes.size == 1:
        only_class = int(unique_classes[0])
        probs_full[:, only_class] = 1.0
        return probs_full.argmax(axis=1), probs_full, FitDiagnostics(pipeline=None, train_probs=None)

    if sample_weight is not None:
        sample_weight = np.asarray(sample_weight, dtype=float)
        # Normalize so mean weight = 1.0. sklearn balances the L2 penalty against
        # the raw weighted loss sum; unnormalized decayed weights (all < 1) would
        # silently strengthen regularization relative to the unweighted fit.
        sample_weight = sample_weight * (len(sample_weight) / sample_weight.sum())

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            solver="newton-cholesky",
            C=1.0 / reg_lambda,
            max_iter=max_iter,
            fit_intercept=True,
        )),
    ])
    # clf__ prefix routes the kwarg to the LogisticRegression step; None passes through legally.
    pipeline.fit(x_train, y_train, clf__sample_weight=sample_weight)

    clf = pipeline.named_steps["clf"]

    def _expand(probs_small: np.ndarray) -> np.ndarray:
        full = np.zeros((probs_small.shape[0], len(CLASS_NAMES)), dtype=float)
        for i, cls in enumerate(clf.classes_):
            full[:, int(cls)] = probs_small[:, i]
        s = full.sum(axis=1, keepdims=True)
        s[s == 0.0] = 1.0
        return full / s

    probs_full = _expand(pipeline.predict_proba(x_test))
    train_probs = _expand(pipeline.predict_proba(x_train))
    y_pred = probs_full.argmax(axis=1)
    return y_pred, probs_full, FitDiagnostics(pipeline=pipeline, train_probs=train_probs)


# ---------------------------------------------------------------------------
# Recency weighting
# ---------------------------------------------------------------------------

def exp_weights(ages: np.ndarray, half_life: Optional[float]) -> Optional[np.ndarray]:
    """Exponential decay weights 0.5 ** (ages / half_life); None = equal weighting."""
    if half_life is None:
        return None
    return 0.5 ** (np.asarray(ages, dtype=float) / float(half_life))


def effective_n(w: Optional[np.ndarray], n_rows: Optional[int] = None) -> float:
    """
    Kish effective sample size (sum w)^2 / sum(w^2).

    When w is None (equal weighting) the raw row count is the effective size;
    pass it via n_rows since it cannot be derived from None.
    """
    if w is None:
        if n_rows is None:
            raise ValueError("effective_n: n_rows required when w is None")
        return float(n_rows)
    w = np.asarray(w, dtype=float)
    denom = float(np.sum(w * w))
    if denom <= 0.0:
        return 0.0
    return float(np.sum(w) ** 2) / denom


# ---------------------------------------------------------------------------
# Fit quality
# ---------------------------------------------------------------------------

def mcfadden_r2(
    y_train: np.ndarray,
    train_probs: Optional[np.ndarray],
    sample_weight: Optional[np.ndarray] = None,
) -> float:
    """
    McFadden pseudo-R2: 1 - ll_model/ll_null on weighted mean cross-entropy,
    where the null model predicts the (weighted) class base rates.

    NaN when degenerate (no train_probs, empty y, zero weight) or ll_null <= 0.
    """
    if train_probs is None:
        return float("nan")
    y = np.asarray(y_train, dtype=int)
    n = y.shape[0]
    if n == 0:
        return float("nan")
    w = np.ones(n, dtype=float) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    w_sum = float(w.sum())
    if w_sum <= 0.0:
        return float("nan")

    eps = 1e-12
    p_model = train_probs[np.arange(n), y]
    ll_model = -float(np.sum(w * np.log(p_model + eps))) / w_sum

    base_rates = np.zeros(len(CLASS_NAMES), dtype=float)
    for k in range(len(CLASS_NAMES)):
        base_rates[k] = float(w[y == k].sum()) / w_sum
    p_null = base_rates[y]
    ll_null = -float(np.sum(w * np.log(p_null + eps))) / w_sum

    if not np.isfinite(ll_null) or ll_null <= 0.0:
        return float("nan")
    return float(1.0 - ll_model / ll_null)


# ---------------------------------------------------------------------------
# Model composition
# ---------------------------------------------------------------------------

def top_drivers(
    pipeline: Optional[Pipeline],
    x_row: np.ndarray,
    target_class_int: int,
    feature_cols: List[str],
    k: int = 3,
) -> Optional[str]:
    """
    Exact logit decomposition for one prediction: contrib = coef[class] * scaled_x.

    Returns top-k features by |contrib| as signed tokens, e.g. '+rsi|-ma50|+beta3m'
    (sign = push direction toward target class, longi_ prefix stripped).

    Returns None (rendered blank) when: pipeline is None, the requested class is
    absent from clf.classes_, or the fit was binary (len(classes_) == 2, where
    sklearn stores a single coefficient row with different semantics).
    """
    if pipeline is None:
        return None
    clf = pipeline.named_steps["clf"]
    classes = [int(c) for c in clf.classes_]
    if len(classes) == 2:
        return None
    if int(target_class_int) not in classes:
        return None

    row_of_class = classes.index(int(target_class_int))
    scaler = pipeline.named_steps["scaler"]
    x_scaled = scaler.transform(np.asarray(x_row, dtype=float).reshape(1, -1))[0]
    contrib = clf.coef_[row_of_class] * x_scaled

    order = np.argsort(-np.abs(contrib))[:k]
    tokens = []
    for i in order:
        name = feature_cols[i]
        if name.startswith("longi_"):
            name = name[len("longi_"):]
        tokens.append(("+" if contrib[i] >= 0.0 else "-") + name)
    return "|".join(tokens)


# ---------------------------------------------------------------------------
# Formatting and matrix I/O (reuse-by-copy of production patterns)
# ---------------------------------------------------------------------------

def format_cell(value, decimals: int = 3) -> str:
    # copied format_prob pattern from longi_winloss_probs.py; strings pass through untouched
    """European comma-decimal formatting, blank for None/NaN; strings unchanged."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if not np.isfinite(value):
        return ""
    return f"{float(value):.{decimals}f}".replace(".", ",")


def read_potdat_layout(potdat_path: Path) -> Tuple[List[str], List[int], List[str]]:
    # copied from longi_winloss_probs.py (read-only production layout source)
    """Return PotDat header row (strings), numeric daynums in header order, and ticker rows in source order."""
    with open(potdat_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        tickers = [row[0] for row in reader if row]

    daynums: List[int] = []
    for col in header[1:]:
        s = str(col).strip()
        if s.isdigit():
            daynums.append(int(s))

    return header, daynums, tickers


def read_existing_matrix_cells(path: Path) -> Dict[str, Dict[int, str]]:
    # copied from longi_winloss_probs.py so partial runs update columns without destroying others
    """Read existing longi matrix values keyed by ticker/daynum, preserving strings."""
    if not path.exists():
        return {}

    out: Dict[str, Dict[int, str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)
        if not header:
            return out

        daynum_cols: List[Tuple[int, int]] = []
        for idx, col in enumerate(header[1:], start=1):
            s = str(col).strip()
            if s.isdigit():
                daynum_cols.append((idx, int(s)))

        for row in reader:
            if not row:
                continue
            ticker = row[0]
            cells = out.setdefault(ticker, {})
            for idx, daynum in daynum_cols:
                cells[daynum] = row[idx] if idx < len(row) else ""
    return out


def write_probability_matrix(
    path: Path,
    ticker_header: str,
    daynums_to_write: List[int],
    ticker_rows: List[str],
    existing_cells: Dict[str, Dict[int, str]],
    overlay_cells: Dict[Tuple[str, int], str],
) -> None:
    # copied from longi_winloss_probs.py so partial runs update columns without destroying others
    """Write one longi matrix using PotDat layout and overlaying recomputed cells."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([ticker_header] + [str(int(d)) for d in daynums_to_write])

        for ticker in ticker_rows:
            prior = existing_cells.get(ticker, {})
            row = [ticker]
            for daynum in daynums_to_write:
                key = (ticker, daynum)
                if key in overlay_cells:
                    row.append(overlay_cells[key])
                else:
                    row.append(prior.get(daynum, ""))
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def append_manifest(script: str, args_str: str, wall_seconds: float, daynums_covered: str) -> None:
    """Append one run line to app/exp/output/manifest.txt (sandbox ground rule 5)."""
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | {script} | {args_str} | "
        f"{wall_seconds:.1f}s | {daynums_covered}\n"
    )
    with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Self-test (Phase 1 acceptance)
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import re

    t0 = time.time()
    rng = np.random.default_rng(42)
    n, p = 600, 5
    feature_names = [f"longi_f{i}" for i in range(p)]

    # Informative synthetic signal: class probabilities driven by features 0 and 1.
    x = rng.normal(size=(n, p))
    logits = np.stack([
        -1.0 * x[:, 0],
        0.2 * x[:, 1],
        1.0 * x[:, 0] + 0.5 * x[:, 1],
    ], axis=1)
    probs_true = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    y = np.array([rng.choice(3, p=pr) for pr in probs_true])
    x_test = rng.normal(size=(3, p))

    print("exp_shared.py self-test (synthetic data, n=%d, p=%d)" % (n, p))

    # (i) sample_weight = ones reproduces the unweighted fit's coefficients
    _, probs_unw, diag_unw = fit_predict_multinomial_ext(x, y, x_test, 0.01, 1000)
    _, probs_ones, diag_ones = fit_predict_multinomial_ext(
        x, y, x_test, 0.01, 1000, sample_weight=np.ones(n)
    )
    coef_unw = diag_unw.pipeline.named_steps["clf"].coef_
    coef_ones = diag_ones.pipeline.named_steps["clf"].coef_
    max_dev = float(np.max(np.abs(coef_unw - coef_ones)))
    assert max_dev < 1e-6, f"(i) FAILED: ones-weight coef deviation {max_dev:.2e}"
    assert np.allclose(probs_unw, probs_ones, atol=1e-9), "(i) FAILED: test probs differ"
    print(f"  (i)  PASS  ones-weight == unweighted (max coef dev {max_dev:.2e})")

    # (ii) strong decay produces different coefficients (old half of history is noise)
    ages = np.arange(n, dtype=float)  # 0 = newest row
    y_drift = y.copy()
    old_mask = ages > n / 2
    y_drift[old_mask] = rng.integers(0, 3, int(old_mask.sum()))
    w_decay = exp_weights(ages, half_life=30.0)
    _, _, diag_eq = fit_predict_multinomial_ext(x, y_drift, x_test, 0.01, 1000)
    _, _, diag_dc = fit_predict_multinomial_ext(
        x, y_drift, x_test, 0.01, 1000, sample_weight=w_decay
    )
    coef_diff = float(np.max(np.abs(
        diag_eq.pipeline.named_steps["clf"].coef_ - diag_dc.pipeline.named_steps["clf"].coef_
    )))
    assert coef_diff > 1e-2, f"(ii) FAILED: decay changed coefs by only {coef_diff:.2e}"
    print(f"  (ii) PASS  strong decay changes coefficients (max coef diff {coef_diff:.3f})")

    # (iii) effective_n of equal weights = n
    en = effective_n(np.ones(n))
    assert abs(en - n) < 1e-9, f"(iii) FAILED: effective_n(ones)={en}"
    assert effective_n(None, n_rows=n) == float(n)
    en_decay = effective_n(w_decay)
    assert en_decay < n, "(iii) FAILED: decayed effective_n should shrink"
    print(f"  (iii) PASS  effective_n(ones)={en:.1f}; effective_n(H=30 decay)={en_decay:.1f}")

    # (iv) mcfadden_r2 = 0.0 at base rates, > 0 for informative signal
    base_rates = np.bincount(y, minlength=3) / n
    r2_null = mcfadden_r2(y, np.tile(base_rates, (n, 1)))
    assert abs(r2_null) < 1e-9, f"(iv) FAILED: base-rate r2 = {r2_null}"
    r2_model = mcfadden_r2(y, diag_unw.train_probs)
    assert r2_model > 0.0, f"(iv) FAILED: informative-signal r2 = {r2_model}"
    print(f"  (iv) PASS  r2(base rates)={r2_null:.2e}; r2(model)={r2_model:.3f}")

    # (v) top_drivers returns 3 signed tokens matching the regex
    token_re = re.compile(r"^[+-]\w+(\|[+-]\w+){2}$")
    drivers = top_drivers(diag_unw.pipeline, x_test[0], CLASS_TO_INT["Win"], feature_names, k=3)
    assert drivers is not None and token_re.match(drivers), f"(v) FAILED: '{drivers}'"
    assert top_drivers(None, x_test[0], CLASS_TO_INT["Win"], feature_names) is None
    print(f"  (v)  PASS  top_drivers -> '{drivers}' (regex ok; None-pipeline -> blank)")

    # format_cell sanity (not a numbered acceptance item, but load-bearing everywhere)
    assert format_cell(0.1234) == "0,123"
    assert format_cell(float("nan")) == ""
    assert format_cell("+rsi|-ma50|+beta3m") == "+rsi|-ma50|+beta3m"
    print("        format_cell: comma decimals, blank NaN, strings untouched")

    wall = time.time() - t0
    append_manifest("exp_shared.py", "(self-test)", wall, "synthetic")
    print(f"** Self-test PASSED in {wall:.1f}s **")
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
