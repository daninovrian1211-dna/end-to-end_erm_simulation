"""Metodologi skoring (spec §3): KRI score, zone, utilization, trend, early warning, risk score,
override, rating, dan enterprise score.

Konvensi presisi: seluruh perhitungan memakai presisi penuh. Pembulatan 1 desimal ROUND_HALF_UP
(fungsi `r1`) hanya dipakai untuk menentukan rating dan untuk tampilan."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF_DIR = ROOT / "data" / "reference"

FLOOR_GAP = 1.5
UTIL_CAP = 1.5
TREND_WINDOW = 3
TREND_THRESHOLD = 0.10
EW_LOOKBACK = 6
EW_HORIZON = 3
ESCALATION_SCORE = 4.5
ESCALATION_WEIGHT = 0.10
ESCALATION_FLOOR = 3.5
CAPITAL_OVERLAY = "Capital Overlay"

ZONES = {1: ("Strong", "Green"), 2: ("Within appetite", "Green"), 3: ("Watch", "Amber"),
         4: ("Tolerance breach", "Red"), 5: ("Limit breach", "Red")}
RATINGS = [(1.5, "Low", "Green"), (2.5, "Low to Moderate", "Green"), (3.5, "Moderate", "Amber"),
           (4.5, "Moderate to High", "Red"), (float("inf"), "High", "Red")]


# ---------- helper ----------
def r1(x: float) -> float:
    """Pembulatan 1 desimal ROUND_HALF_UP (identik dengan reference_calc.py)."""
    return float(Decimal(str(round(float(x), 10))).quantize(Decimal("0.1"), ROUND_HALF_UP))


def rating(score: float) -> tuple[str, str]:
    s = r1(score)
    for upper, label, color in RATINGS:
        if s < upper:
            return label, color
    raise ValueError(score)


def load_reference() -> dict[str, pd.DataFrame]:
    return {
        "risk_appetite": pd.read_csv(REF_DIR / "risk_appetite.csv"),
        "risk_weights": pd.read_csv(REF_DIR / "risk_weights.csv"),
        "judgment_overrides": pd.read_csv(REF_DIR / "judgment_overrides.csv"),
        "emerging_risks": pd.read_csv(REF_DIR / "emerging_risks.csv"),
    }


# ---------- §3.1 ----------
def kri_score(x: float, direction: str, cuts: list[float]) -> int:
    x = abs(x)  # KRI bertanda dihitung absolut; nilai KRI engine sudah non-negatif
    for i, c in enumerate(cuts, 1):
        if (x <= c) if direction == "lower" else (x >= c):
            return i
    return 5


# ---------- §3.6 ----------
def utilization(x: float, direction: str, c4: float) -> float:
    u = abs(x) / c4 if direction == "lower" else (c4 / x if x > 0 else UTIL_CAP)
    return min(u, UTIL_CAP)


def trend_label(values: np.ndarray, direction: str, c1: float, c4: float) -> str:
    """Δ = rata-rata 3 bulan terakhir − 3 bulan sebelumnya, dinormalisasi |c4 − c1|."""
    if len(values) < 2 * TREND_WINDOW or np.isnan(values[-2 * TREND_WINDOW:]).any():
        return "Insufficient history"
    delta = values[-TREND_WINDOW:].mean() - values[-2 * TREND_WINDOW:-TREND_WINDOW].mean()
    norm = delta / abs(c4 - c1)
    worsening = norm if direction == "lower" else -norm
    if worsening > TREND_THRESHOLD:
        return "Deteriorating"
    if worsening < -TREND_THRESHOLD:
        return "Improving"
    return "Stable"


def early_warning(values: np.ndarray, score: int, direction: str, cuts: list[float]) -> bool:
    """Skor ≤ 3 dan proyeksi garis OLS 6 bulan terakhir melewati cut-point berikutnya dalam ≤ 3 bulan."""
    if score > 3 or len(values) < EW_LOOKBACK or np.isnan(values[-EW_LOOKBACK:]).any():
        return False
    y = values[-EW_LOOKBACK:]
    t = np.arange(EW_LOOKBACK)
    slope, intercept = np.polyfit(t, y, 1)
    proj = intercept + slope * (EW_LOOKBACK - 1 + np.arange(1, EW_HORIZON + 1))
    nxt = cuts[score - 1]
    return bool((proj > nxt).any() if direction == "lower" else (proj < nxt).any())


def score_kris(kri_values: pd.DataFrame, risk_appetite: pd.DataFrame) -> pd.DataFrame:
    """kri_values: long (period, kri_id, value) → kri_monthly (spec §8.4)."""
    ra = risk_appetite.set_index("kri_id")
    wide = kri_values.pivot(index="period", columns="kri_id", values="value").sort_index()
    rows = []
    for kid in ra.index:
        r = ra.loc[kid]
        cuts = [r.c1, r.c2, r.c3, r.c4]
        series = wide[kid].to_numpy(dtype=float)
        for i, period in enumerate(wide.index):
            x = series[i]
            sc = kri_score(x, r.direction, cuts)
            hist = series[: i + 1]
            rows.append(dict(period=period, kri_id=kid, risk_type=r.risk_type, value=x, score=sc,
                             zone=ZONES[sc][0], color=ZONES[sc][1],
                             utilization=utilization(x, r.direction, r.c4),
                             trend_label=trend_label(hist, r.direction, r.c1, r.c4),
                             early_warning_flag=early_warning(hist, sc, r.direction, cuts)))
    return pd.DataFrame(rows).sort_values(["period", "kri_id"], ignore_index=True)


# ---------- §3.2–3.4 ----------
def override_delta(overrides: pd.DataFrame, risk_type: str, period: str) -> float:
    o = overrides[(overrides.risk_type == risk_type) & (overrides.period <= period) & (overrides.valid_until >= period)]
    if o.empty:
        return 0.0
    o = o.sort_values("period").iloc[-1]
    delta = float(o.final_score) - float(o.model_score)
    if abs(delta) > 1.0 + 1e-9:
        raise ValueError(f"override {risk_type} melebihi ±1,0")
    return delta


def aggregate_risk(scores: pd.DataFrame, risk_appetite: pd.DataFrame, overrides: pd.DataFrame,
                   period: str) -> pd.DataFrame:
    """scores: period × kri (kolom kri_id, score). Return satu baris per risk type."""
    w = risk_appetite.set_index("kri_id").kri_weight
    rt = risk_appetite.set_index("kri_id").risk_type
    df = scores.assign(weight=scores.kri_id.map(w), risk_type=scores.kri_id.map(rt))
    df = df[df.risk_type != CAPITAL_OVERLAY]
    rows = []
    for risk, g in df.groupby("risk_type", sort=False):
        weighted = float((g.score * g.weight).sum())
        floor = float(g.score.max()) - FLOOR_GAP
        model = max(weighted, floor)
        delta = override_delta(overrides, risk, period)
        final = min(5.0, max(1.0, model + delta))
        label, color = rating(final)
        rows.append(dict(period=period, risk_type=risk, weighted_score=weighted, floor_score=floor,
                         model_score=model, override_delta=delta, final_score=final, rating=label, color=color))
    return pd.DataFrame(rows)


# ---------- §3.5–3.6 ----------
def enterprise_score(risk_scores: pd.DataFrame, weights: pd.DataFrame) -> float:
    w = weights.set_index("risk_type").materiality_weight
    s = risk_scores.set_index("risk_type").final_score
    ent = float((s * w.reindex(s.index)).sum())
    ent = max(ent, float(s.max()) - FLOOR_GAP)
    if any((s >= ESCALATION_SCORE) & (w.reindex(s.index) >= ESCALATION_WEIGHT)):
        ent = max(ent, ESCALATION_FLOOR)
    return ent


def limit_utilization(kri_rows: pd.DataFrame, risk_appetite: pd.DataFrame, weights: pd.DataFrame) -> float:
    w_kri = risk_appetite.set_index("kri_id").kri_weight
    k = kri_rows[kri_rows.risk_type != CAPITAL_OVERLAY]
    per_risk = (k.utilization * k.kri_id.map(w_kri)).groupby(k.risk_type).sum()
    w = weights.set_index("risk_type").materiality_weight
    return float((per_risk.reindex(w.index) * w).sum() * 100)


def run_scoring(kri_values: pd.DataFrame, ref: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    ref = ref or load_reference()
    ra, weights, ov = ref["risk_appetite"], ref["risk_weights"], ref["judgment_overrides"]
    kri_monthly = score_kris(kri_values, ra)
    order = list(weights.risk_type)
    risk_rows, ent_rows = [], []
    emerging = int(ref["emerging_risks"].status.isin(["Monitor", "Watch", "Act"]).sum())
    for period, g in kri_monthly.groupby("period"):
        rs = aggregate_risk(g, ra, ov, period)
        rs["_o"] = rs.risk_type.map({r: i for i, r in enumerate(order)})
        rs = rs.sort_values("_o").drop(columns="_o")
        risk_rows.append(rs)
        ent = enterprise_score(rs, weights)
        label, _ = rating(ent)
        k = g[g.risk_type != CAPITAL_OVERLAY]
        ent_rows.append(dict(period=period, enterprise_score=ent, rating=label,
                             limit_utilization=limit_utilization(g, ra, weights),
                             tolerance_breaches=int((k.score >= 4).sum()), limit_breaches=int((k.score == 5).sum()),
                             emerging_count=emerging))
    return {"kri_monthly": kri_monthly,
            "risk_scores_monthly": pd.concat(risk_rows, ignore_index=True),
            "enterprise_profile_monthly": pd.DataFrame(ent_rows)}


def profile_table(risk_scores: pd.DataFrame, enterprise: pd.DataFrame, period: str) -> pd.DataFrame:
    """Tabel Enterprise Risk Profile (tampilan, dibulatkan 1 desimal) — format ringkasan spec §4."""
    rs = risk_scores[risk_scores.period == period]
    rows = [dict(risk=r.risk_type, score=r1(r.final_score),
                 model=r1(r.model_score) if abs(r.override_delta) > 0 else None, rating=r.rating, color=r.color)
            for r in rs.itertuples()]
    e = enterprise[enterprise.period == period].iloc[0]
    rows.append(dict(risk="Enterprise", score=r1(e.enterprise_score), model=None, rating=e.rating,
                     color=rating(e.enterprise_score)[1]))
    return pd.DataFrame(rows)
