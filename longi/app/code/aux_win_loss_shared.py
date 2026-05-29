"""
Shared utilities for Win/Loss production and QA scripts.

This module centralizes:
- feature/target loading
- per-ticker multinomial model fitting
- prediction/error metric helpers
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


FEATURE_FILES: List[str] = [
    "longi_beta3m.csv",
    "longi_coreindex.csv",
    "longi_coreindexRSI.csv",
    "longi_GICS_3m.csv",
    "longi_ma10.csv",
    "longi_ma20.csv",
    "longi_ma50.csv",
    "longi_macd_signal.csv",
    "longi_median_10d.csv",
    "longi_median_30d.csv",
    "longi_median_50d.csv",
    "longi_PdivMA50.csv",
    "longi_per1m.csv",
    "longi_per3m.csv",
    "longi_rsi.csv",
    "longi_Sector2_3m.csv",
    "longi_sh3m.csv",
    "longi_spr100d.csv",
    "longi_stepup100.csv",
    "longi_stepup40.csv",
    "longi_vola100d.csv",
    "longi_vola20d.csv",
]

CLASS_NAMES = ["Loss", "NoLoss", "Win"]
CLASS_TO_INT = {name: idx for idx, name in enumerate(CLASS_NAMES)}


@dataclass(frozen=True)
class TargetSpec:
    """Target definition for model training."""

    key: str
    target_file: str
    win_threshold: float
    loss_threshold: float = 0.0


TARGET_SPECS: List[TargetSpec] = [
    TargetSpec(key="20d", target_file="future_gain20d.csv", win_threshold=6.0, loss_threshold=0.0),
    TargetSpec(key="50d", target_file="future_gain50d.csv", win_threshold=10.0, loss_threshold=0.0),
]


def read_indicator_matrix(path: Path) -> pd.DataFrame:
    """Read one indicator CSV as numeric matrix indexed by ticker."""
    df = pd.read_csv(path, sep=";", decimal=",")
    key_col = df.columns[0]
    df = df.rename(columns={key_col: "ticker"})
    df["ticker"] = df["ticker"].astype(str)

    day_cols = [col for col in df.columns if str(col).strip().isdigit()]
    mat = df.set_index("ticker")[day_cols].apply(pd.to_numeric, errors="coerce")
    mat.columns = [int(c) for c in mat.columns]
    return mat


def stack_non_null(mat: pd.DataFrame) -> pd.Series:
    """Stack dataframe and keep non-null values."""
    try:
        return mat.stack(future_stack=True).dropna()
    except TypeError:
        return mat.stack(dropna=True)


def ensure_files_exist(paths: Iterable[Path]) -> None:
    """Raise if any required files are missing."""
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))


def get_max_daynum_from_potdat(potdat_path: Path) -> int:
    """Read maximum numeric daynum from PotDat header."""
    header = pd.read_csv(potdat_path, sep=";", decimal=",", nrows=0).columns.tolist()
    daynums = [int(c) for c in header[1:] if str(c).strip().isdigit()]
    if not daynums:
        raise ValueError(f"No numeric daynum columns found in {potdat_path}")
    return int(max(daynums))


def get_non_caret_tickers_from_potdat(potdat_path: Path) -> List[str]:
    """Return unique non-caret tickers in source order."""
    df = pd.read_csv(potdat_path, sep=";", decimal=",", usecols=[0])
    tickers = df.iloc[:, 0].astype(str)
    non_caret = tickers[~tickers.str.startswith("^")]
    return non_caret.drop_duplicates().tolist()


def build_feature_frame(output_dir: Path) -> pd.DataFrame:
    """Build shared feature dataframe from all configured feature files."""
    feature_paths = [output_dir / fname for fname in FEATURE_FILES]
    ensure_files_exist(feature_paths)

    series_list: List[pd.Series] = []
    for feature_path in feature_paths:
        feature_name = feature_path.stem
        mat = read_indicator_matrix(feature_path)
        s = stack_non_null(mat).rename(feature_name)
        series_list.append(s)

    x_df = pd.concat(series_list, axis=1, join="inner").reset_index()
    x_df.columns = ["ticker", "daynum"] + [Path(f).stem for f in FEATURE_FILES]
    x_df["ticker"] = x_df["ticker"].astype(str)
    x_df["daynum"] = x_df["daynum"].astype(int)
    return x_df


def label_from_gain(gain: float, win_threshold: float, loss_threshold: float) -> str:
    """Map numeric gain to class label."""
    if gain > win_threshold:
        return CLASS_NAMES[2]  # "Win"
    if gain < loss_threshold:
        return CLASS_NAMES[0]  # "Loss"
    return CLASS_NAMES[1]  # "NoLoss"


def build_labeled_dataset(feature_df: pd.DataFrame, output_dir: Path, spec: TargetSpec) -> pd.DataFrame:
    """Join features with selected target and add class labels."""
    target_path = output_dir / spec.target_file
    ensure_files_exist([target_path])

    y_mat = read_indicator_matrix(target_path)
    y_series = stack_non_null(y_mat).rename("target_gain")
    y_df = y_series.reset_index()
    y_df.columns = ["ticker", "daynum", "target_gain"]
    y_df["ticker"] = y_df["ticker"].astype(str)
    y_df["daynum"] = y_df["daynum"].astype(int)

    data = feature_df.merge(y_df, on=["ticker", "daynum"], how="inner")
    data["y_label"] = data["target_gain"].apply(
        lambda g: label_from_gain(float(g), spec.win_threshold, spec.loss_threshold)
    )
    data["y_int"] = data["y_label"].map(CLASS_TO_INT).astype(int)
    return data


def standardize_fit(x_train: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Compute train mean/std with zero-std guard."""
    mean = np.mean(x_train, axis=0)
    std = np.std(x_train, axis=0)
    std[std == 0.0] = 1.0
    return mean, std


class SoftmaxRegressor:
    """Multinomial softmax regression with L2 regularization."""

    def __init__(self, reg_lambda: float = 0.01, max_iter: int = 250) -> None:
        self.reg_lambda = reg_lambda
        self.max_iter = max_iter
        self.weights: Optional[np.ndarray] = None

    def fit(self, x: np.ndarray, y: np.ndarray, n_classes: int) -> None:
        n_samples, n_features = x.shape
        x_aug = np.hstack([x, np.ones((n_samples, 1), dtype=float)])
        y_onehot = np.eye(n_classes)[y]
        w0 = np.zeros((n_features + 1, n_classes), dtype=float)

        def loss_grad(w_flat: np.ndarray) -> Tuple[float, np.ndarray]:
            w = w_flat.reshape(n_features + 1, n_classes)
            logits = x_aug @ w
            logits -= logits.max(axis=1, keepdims=True)
            exp_logits = np.exp(logits)
            probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
            eps = 1e-12

            ce = -np.sum(y_onehot * np.log(probs + eps)) / n_samples
            reg = 0.5 * self.reg_lambda * np.sum(w[:-1, :] ** 2)
            loss = ce + reg

            grad = (x_aug.T @ (probs - y_onehot)) / n_samples
            grad[:-1, :] += self.reg_lambda * w[:-1, :]
            return loss, grad.reshape(-1)

        result = minimize(
            fun=lambda z: loss_grad(z)[0],
            x0=w0.reshape(-1),
            jac=lambda z: loss_grad(z)[1],
            method="L-BFGS-B",
            options={"maxiter": self.max_iter},
        )
        self.weights = result.x.reshape(n_features + 1, n_classes)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("Model is not fitted.")
        x_aug = np.hstack([x, np.ones((x.shape[0], 1), dtype=float)])
        logits = x_aug @ self.weights
        logits -= logits.max(axis=1, keepdims=True)
        exp_logits = np.exp(logits)
        return exp_logits / exp_logits.sum(axis=1, keepdims=True)


def fit_predict_multinomial(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    reg_lambda: float,
    max_iter: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Fit multinomial model and return predicted class indices + full class probs.

    Handles missing classes in train split by re-indexing and expanding back to full classes.
    """
    unique_classes = np.unique(y_train)
    probs_full = np.zeros((x_test.shape[0], len(CLASS_NAMES)), dtype=float)

    if unique_classes.size == 1:
        only_class = int(unique_classes[0])
        probs_full[:, only_class] = 1.0
        return probs_full.argmax(axis=1), probs_full

    class_old_to_new = {old: idx for idx, old in enumerate(unique_classes)}
    class_new_to_old = {idx: old for old, idx in class_old_to_new.items()}
    y_train_small = np.array([class_old_to_new[int(v)] for v in y_train], dtype=int)

    model = SoftmaxRegressor(reg_lambda=reg_lambda, max_iter=max_iter)
    model.fit(x_train, y_train_small, n_classes=unique_classes.size)
    probs_small = model.predict_proba(x_test)

    for small_idx in range(probs_small.shape[1]):
        old_idx = class_new_to_old[small_idx]
        probs_full[:, old_idx] = probs_small[:, small_idx]

    probs_sum = probs_full.sum(axis=1, keepdims=True)
    probs_sum[probs_sum == 0.0] = 1.0
    probs_full = probs_full / probs_sum
    y_pred = probs_full.argmax(axis=1)
    return y_pred, probs_full


def compute_error_counts(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, int]:
    """Compute project-standard error counts."""
    loss = CLASS_TO_INT[CLASS_NAMES[0]]   # CLASS_NAMES order is Loss=0, NoLoss=1, Win=2
    nothing = CLASS_TO_INT[CLASS_NAMES[1]]
    win = CLASS_TO_INT[CLASS_NAMES[2]]

    first_order = int(
        np.sum(((y_pred == win) & (y_true == loss)) | ((y_pred == loss) & (y_true == win)))
    )
    second_order = int(np.sum((y_pred == nothing) & ((y_true == loss) | (y_true == win))))
    signal_vs_nothing = int(np.sum(((y_pred == loss) | (y_pred == win)) & (y_true == nothing)))
    return {
        "first_order_error": first_order,
        "second_order_error": second_order,
        "signal_vs_nothing_error": signal_vs_nothing,
    }

