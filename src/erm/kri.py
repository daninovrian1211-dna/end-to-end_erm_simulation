"""Perhitungan nilai 42 KRI + CAP01 dari data raw (spec §4, definisi operasional §8.2).

Modul ini hanya menghitung NILAI KRI. Skoring, trend, dan early warning ada di scoring.py."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORT_PERIODS = pd.period_range("2025-10", "2026-09", freq="M").strftime("%Y-%m").tolist()
RAW_FILES = ["balance_sheet_monthly", "capital_monthly", "financing_portfolio", "deposits_monthly", "top_depositors",
             "maturity_profile", "market_positions", "investment_portfolio", "rate_of_return_monthly",
             "operational_events", "compliance_events", "legal_cases", "complaints", "sentiment_monthly",
             "strategic_monthly"]
BELOW_IDA = {"idA-(sy)", "idBBB+(sy)", "idBBB(sy)", "idBBB-(sy)", "idBB+(sy)", "idBB(sy)", "idB(sy)"}
REPEAT_WINDOW_OPS = 3      # OR02, OR04, OR05: rolling 3 bulan
ROLLING_CP03 = 12          # CP03: rolling 12 bulan
DPS_AGE_DAYS = 90
LEGAL_AGE_DAYS = 365
# Presisi pengukuran nilai KRI: 6 desimal, menghilangkan noise floating-point/pembulatan data granular
# (mis. 0,45 tersimpan sebagai 0,4500000000000002) yang dapat menggeser skor tepat di cut-point.
VALUE_DECIMALS = 6


def load_raw(raw_dir: Path | str = ROOT / "data" / "raw") -> dict[str, pd.DataFrame]:
    raw_dir = Path(raw_dir)
    return {name: pd.read_csv(raw_dir / f"{name}.csv") for name in RAW_FILES}


def _shift(period: str, months: int) -> str:
    return (pd.Period(period, freq="M") + months).strftime("%Y-%m")


def _window(period: str, n: int) -> list[str]:
    return [_shift(period, -i) for i in range(n)]


def _end(period: str) -> pd.Timestamp:
    return pd.Period(period, freq="M").end_time.normalize()


def compute_kri_values(raw: dict[str, pd.DataFrame], periods: list[str] | None = None,
                       profile: dict | None = None) -> pd.DataFrame:
    """Return DataFrame long: period, kri_id, value."""
    periods = periods or REPORT_PERIODS
    profile = profile or yaml.safe_load((ROOT / "config" / "bank_profile.yaml").read_text(encoding="utf-8"))
    sl = profile["slsi"]
    bs = raw["balance_sheet_monthly"].pivot(index="period", columns="line_item", values="amount")
    cap = raw["capital_monthly"].set_index("period")
    fin = raw["financing_portfolio"]
    dep = raw["deposits_monthly"]
    inv = raw["investment_portfolio"]
    mat = raw["maturity_profile"]
    ops = raw["operational_events"]
    cmp_ = raw["compliance_events"].copy()
    cmp_["target_remediation_date"] = pd.to_datetime(cmp_.target_remediation_date)
    cmp_["closed_date"] = pd.to_datetime(cmp_.closed_date)
    lg = raw["legal_cases"]
    cpl = raw["complaints"]
    sen = raw["sentiment_monthly"]
    ror = raw["rate_of_return_monthly"].set_index("period")
    stg = raw["strategic_monthly"].set_index("period")

    total_assets = bs[[c for c in bs.columns if c in {
        "kas_giro_bi_gwm_wajib", "kas_giro_bi_excess", "penempatan_bank_lain", "sukuk_fvoci", "sukuk_amortized_cost",
        "pembiayaan_bruto", "cadangan_kerugian", "aset_lain"}]].sum(axis=1)
    dpk = bs[["giro_wadiah", "tabungan", "deposito_mudharabah"]].sum(axis=1)

    # SLSI: net outflow dikalibrasi ke anchor 8.750 (keputusan Fase 2)
    runoff = sl["runoff_30d"]
    gross_out = (dep.assign(x=dep.balance * dep.runoff_assumption).groupby("period").x.sum()
                 + runoff["other_funding"] * bs["pendanaan_lain"])
    k = sl["net_outflow_30d_anchor"] / gross_out[sl["anchor_period"]]

    rows = []
    for p in periods:
        v = {}
        capital = cap.at[p, "capital_kpmm"]
        f = fin[fin.period == p]
        F = f.outstanding.sum()
        u = f[f.segment == "UMKM"]
        v["CR01"] = f.loc[f.collectibility >= 3, "outstanding"].sum() / F * 100
        v["CR02"] = u.loc[u.collectibility >= 3, "outstanding"].sum() / u.outstanding.sum() * 100
        v["CR03"] = f.loc[f.collectibility == 2, "outstanding"].sum() / F * 100
        v["CR04"] = f.outstanding.nlargest(10).sum() / F * 100
        v["CR05"] = f.groupby("sector").outstanding.sum().max() / F * 100

        mp = raw["market_positions"][raw["market_positions"].period == p]
        v["MR01"] = mp.net_position.abs().sum() / capital * 100
        h = inv[inv.period == p]
        fv = h[h.classification == "FVOCI"]
        v["MR02"] = (fv.market_value * fv.modified_duration).sum() * 0.01 / capital * 100
        m = mat[(mat.period == p) & (mat.bucket != ">12m")]
        v["MR03"] = abs((m.rsa - m.rsl).sum()) / total_assets[p] * 100

        unenc = h[~h.encumbered_flag.astype(bool)]
        carrying = np.where(unenc.classification == "FVOCI", unenc.market_value, unenc.face_value).sum()
        liquid = bs.at[p, "kas_giro_bi_excess"] + bs.at[p, "penempatan_bank_lain"] + (1 - sl["haircut_sukuk_unencumbered"]) * carrying
        v["LQ01"] = liquid / (k * gross_out[p]) * 100
        v["LQ02"] = bs.at[p, "pembiayaan_bruto"] / dpk[p] * 100
        td = raw["top_depositors"]
        v["LQ03"] = td.loc[td.period == p, "balance"].sum() / dpk[p] * 100
        m1 = mat[(mat.period == p) & (mat.bucket == "<=1m")].iloc[0]
        v["LQ04"] = max(0.0, m1.liabilities_maturing - m1.assets_maturing) / total_assets[p] * 100
        d3 = dpk[_shift(p, -3)]
        v["LQ05"] = max(0.0, (d3 - dpk[p]) / d3 * 100)

        o3 = ops[ops.period.isin(_window(p, REPEAT_WINDOW_OPS))]
        v["OR01"] = float((ops.period == p).sum())
        v["OR02"] = float((o3.severity == "High").sum())
        v["OR03"] = ops.loc[ops.period.isin(_window(p, 12)), "net_loss"].sum() / cap.at[p, "gross_income_ttm"] * 100
        v["OR04"] = o3.repeat_flag.astype(bool).mean() * 100
        age = (pd.Timestamp("2026-09-30") - pd.to_datetime(o3.event_date)).dt.days
        breach = np.where(o3.resolution_days.notna(), o3.resolution_days > o3.sla_days, age > o3.sla_days)
        v["OR05"] = breach.mean() * 100

        v["ST01"] = abs(stg.at[p, "financing_growth_yoy"] - stg.at[p, "financing_growth_target"])
        v["ST02"] = cap.at[p, "profit_ytd"] / cap.at[p, "profit_budget_ytd"] * 100
        v["ST03"] = stg.at[p, "cost_to_income"]
        v["ST04"] = stg.at[p, "initiatives_delayed"] / stg.at[p, "initiatives_total"] * 100

        end = _end(p)
        raised = cmp_[cmp_.period <= p]
        is_open = raised.closed_date.isna() | (raised.closed_date > end)
        v["CP01"] = float((cmp_.period.isin(_window(p, 3)) & cmp_.source.isin(["regulator", "internal audit"])).sum())
        v["CP02"] = float(((raised.severity == "High") & (raised.target_remediation_date < end) & is_open).sum())
        c12 = cmp_[cmp_.period.isin(_window(p, ROLLING_CP03))]
        v["CP03"] = c12.repeat_flag.astype(bool).mean() * 100
        dps_age = (end - pd.to_datetime(raised.period + "-01")).dt.days
        v["CP04"] = float(((raised.source == "DPS") & is_open & (dps_age > DPS_AGE_DAYS)).sum())

        open_cases = lg[(lg.open_period <= p) & (lg.closed_period.isna() | (lg.closed_period > p))]
        v["LG01"] = float(len(open_cases))
        v["LG02"] = float((open_cases.severity == "High").sum())
        v["LG03"] = open_cases.potential_loss.sum() / capital * 100
        case_age = (end - pd.to_datetime(open_cases.open_period + "-01")).dt.days
        v["LG04"] = (case_age > LEGAL_AGE_DAYS).mean() * 100 if len(open_cases) else 0.0

        n_now, n_prev = (cpl.period == p).sum(), (cpl.period == _shift(p, -1)).sum()
        c = cpl[cpl.period == p]
        v["RP01"] = (n_now / n_prev - 1) * 100
        v["RP02"] = (c.severity == "Severe").mean() * 100
        v["RP03"] = (c.resolution_days > c.sla_days).fillna(False).astype(bool).mean() * 100
        s = sen[sen.period == p]
        v["RP04"] = s.negative_mentions.sum() / s.mentions.sum() * 100

        dd = dep[(dep.period == p) & (dep["product"] == "deposito_mudharabah")].iloc[0]
        v["RR01"] = dd.market_benchmark_rate - dd.equivalent_rate
        v["RR02"] = ror.at[p, "expected_depositor_return"] - ror.at[p, "actual_depositor_return"]
        v["RR03"] = ror.at[p, "nim"]
        v["RR04"] = f.loc[(f.margin_type == "fixed") & (f.remaining_tenor_months > 36), "outstanding"].sum() / F * 100

        mv = h.market_value.sum()
        v["IV01"] = h[h.issuer_type != "sovereign"].groupby("issuer").market_value.sum().max() / mv * 100
        v["IV02"] = h.loc[h.rating.isin(BELOW_IDA), "market_value"].sum() / mv * 100
        fv3 = inv[(inv.period == _shift(p, -3)) & (inv.classification == "FVOCI")].market_value.sum()
        v["IV03"] = max(0.0, (1 - fv.market_value.sum() / fv3) * 100)
        v["IV04"] = (h.market_value * h.modified_duration).sum() / mv

        v["CAP01"] = capital / cap.at[p, "atmr"] * 100
        rows += [dict(period=p, kri_id=kid, value=round(float(val), VALUE_DECIMALS)) for kid, val in v.items()]
    return pd.DataFrame(rows)


def build_kri_monthly(raw_dir: Path | str = ROOT / "data" / "raw") -> pd.DataFrame:
    """Nilai 43 indikator (42 KRI + CAP01) per bulan pelaporan, dihitung dari data raw."""
    return compute_kri_values(load_raw(raw_dir))
