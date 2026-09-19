"""Kalibrasi generator: periode, jalur target KRI (value_start → value_target), dan alat penyesuaian.

Alur: generator granular membuat data "mentah realistis" (distribusi sektor, akad, severity, root cause),
lalu fungsi di modul ini (raking / alokasi rolling count) menyesuaikan data sehingga KRI yang dihitung
dari data raw mengikuti jalur target. Nilai Sep-2026 dibuat persis sama dengan value_target.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
REF_DIR = ROOT / "data" / "reference"
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "data" / "raw"

REPORT_PERIODS = pd.period_range("2025-10", "2026-09", freq="M").strftime("%Y-%m").tolist()
# 3 bulan lookback agar KRI berjendela (Δ 3 bulan, rolling 3 bulan, MoM) terdefinisi sejak Okt-2025.
MONTHLY_PERIODS = pd.period_range("2025-07", "2026-09", freq="M").strftime("%Y-%m").tolist()
# Log event (operasional, kepatuhan) memuat 12 bulan lookback untuk KRI rolling 12 bulan.
EVENT_PERIODS = pd.period_range("2024-10", "2026-09", freq="M").strftime("%Y-%m").tolist()
LOOKBACK = len(MONTHLY_PERIODS) - len(REPORT_PERIODS)  # 3
REPORTING_DATE = pd.Timestamp("2026-09-30")

NOISE_FRACTION = 0.015  # noise = 1,5% × |c4 − c1|, nol pada Okt-2025 dan Sep-2026

# Bentuk jalur (12 bulan Okt-2025..Sep-2026, 0 → 1) sesuai storyline spec
SHAPES = {
    "linear": np.linspace(0, 1, 12),
    # DPK turun dan maturity gap melebar pada 4 bulan terakhir (Jun–Sep 2026)
    "late4": np.array([0, .02, .04, .06, .08, .10, .12, .15, .40, .62, .82, 1.0]),
    # lonjakan insiden digital sejak Jun-2026
    "jun": np.array([0, .03, .06, .09, .12, .15, .18, .22, .60, .85, 1.0, 1.0]),
    # KRI kuartalan: berubah per kuartal
    "quarterly": np.array([0, 0, 0, 1 / 3, 1 / 3, 1 / 3, 2 / 3, 2 / 3, 2 / 3, 1, 1, 1]),
}
SHAPE_BY_KRI = {"LQ01": "late4", "LQ04": "late4", "OR01": "jun", "OR03": "jun", "ST04": "quarterly"}

# KRI yang dirancang eksplisit per bulan (integer / event naratif) atau diturunkan dari agregat
NO_NOISE = {"OR01", "OR02", "CP01", "CP02", "CP04", "LG01", "LG02", "LG03", "LG04", "ST04",
            "IV01", "IV02", "LQ02", "LQ05", "RP01"}
INTEGER_KRI = {"OR01", "OR02", "CP01", "CP02", "CP04", "LG01", "LG02"}

# Storyline komplain: stabil, lalu lonjakan Ags–Sep 2026 (gangguan mobile banking)
RP01_PATH = np.array([2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.5, 3.0, 2.0, 3.0, 3.5, 4.0, 5.0, 18.0, 25.0])


def load_risk_appetite() -> pd.DataFrame:
    return pd.read_csv(REF_DIR / "risk_appetite.csv")


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def month_end(period: str) -> pd.Timestamp:
    return pd.Period(period, freq="M").end_time.normalize()


def month_start(period: str) -> pd.Timestamp:
    return pd.Period(period, freq="M").start_time


def kri_targets(rng: np.random.Generator) -> pd.DataFrame:
    """Jalur target seluruh KRI untuk MONTHLY_PERIODS (lookback = value_start)."""
    ra = load_risk_appetite()
    out = {}
    for row in ra.itertuples(index=False):
        z = rng.normal(0.0, 1.0, len(MONTHLY_PERIODS))  # selalu diambil → urutan RNG stabil
        shape = SHAPES[SHAPE_BY_KRI.get(row.kri_id, "linear")]
        s = np.concatenate([np.zeros(LOOKBACK), shape])
        path = row.value_start_2025_10 + (row.value_target_2026_09 - row.value_start_2025_10) * s
        if row.kri_id not in NO_NOISE:
            noise = z * NOISE_FRACTION * abs(row.c4 - row.c1)
            noise[LOOKBACK] = 0.0
            noise[-1] = 0.0
            path = path + noise
        if row.kri_id in INTEGER_KRI:
            path = np.round(path)
        out[row.kri_id] = path
    out["RP01"] = RP01_PATH.copy()
    return pd.DataFrame(out, index=pd.Index(MONTHLY_PERIODS, name="period"))


def rake(weights: np.ndarray, partitions: list[tuple[np.ndarray, np.ndarray]],
         max_iter: int = 2000, tol: float = 1e-11) -> np.ndarray:
    """Iterative proportional fitting. partitions = [(label kode 0..k-1, target per kode)]."""
    w = np.asarray(weights, dtype=float).copy()
    for _ in range(max_iter):
        for labels, targets in partitions:
            sums = np.bincount(labels, weights=w, minlength=len(targets))
            factor = np.divide(targets, sums, out=np.zeros_like(targets, dtype=float), where=sums > 0)
            w *= factor[labels]
        err = max(np.max(np.abs(np.bincount(l, weights=w, minlength=len(t)) - t) / np.maximum(t, 1e-9))
                  for l, t in partitions)
        if err < tol:
            return w
    raise RuntimeError(f"raking tidak konvergen (err={err:.2e})")


def allocate_rolling(target_rolling: np.ndarray, window: int, initial: list[int],
                     cap: np.ndarray | None = None) -> np.ndarray:
    """Alokasi count bulanan sehingga jumlah rolling `window` bulan ≈ target (greedy, non-negatif).

    initial = count untuk (window-1) bulan sebelum target pertama."""
    counts = list(initial)
    for i, tgt in enumerate(target_rolling):
        prev = sum(counts[-(window - 1):]) if window > 1 else 0
        c = max(0, int(round(tgt)) - prev)
        if cap is not None:
            c = min(c, int(cap[i]))
        counts.append(c)
    return np.array(counts[len(initial):])


def smooth_noise(rng: np.random.Generator, n: int, scale: float) -> np.ndarray:
    return rng.normal(0.0, scale, n)
