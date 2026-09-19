"""Enterprise stress testing (spec §5.1–5.4).

Aturan transmisi dibaca dari config/stress_parameters.yaml dan diterapkan pada nilai KRI Sep-2026
hasil engine (kri_monthly). Skoring ulang memakai fungsi di scoring.py; tidak ada logika skoring di sini.
Horizon 12 bulan, neraca statis, tanpa management action (gross stress impact)."""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import yaml

from . import scoring

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ["baseline", "adverse", "severe"]
# KRI yang secara desain dapat membaik saat stress (spec §5.2: growth melambat → deviasi mengecil)
MAY_IMPROVE = {"ST01"}


def load_stress_parameters() -> dict:
    return yaml.safe_load((ROOT / "config" / "stress_parameters.yaml").read_text(encoding="utf-8"))


def load_macro_scenarios() -> pd.DataFrame:
    return pd.read_csv(scoring.REF_DIR / "macro_scenarios.csv").set_index("variable")


# ---------- interpreter aturan §5.2 ----------
def _drivers(macro: pd.Series, conv: dict) -> tuple[float, float]:
    return conv["gdp_reference"] - float(macro["gdp_growth"]), float(macro["policy_rate_shift"])


def _additive(v, rule, m, dg, bps, conv, ctx):
    return v + rule.get("gdp_coef", 0.0) * dg + rule.get("bps_coef", 0.0) * bps / conv["bps_per_pct"]


def _multiple_of_delta(v, rule, m, dg, bps, conv, ctx):
    ref = rule["ref_kri"]
    return v + rule["multiplier"] * (ctx["stressed"][ref] - ctx["base"][ref])


def _scale_by_variable(v, rule, m, dg, bps, conv, ctx):
    return v * (1 + float(m[rule["variable"]]) / 100)


def _scale_by_variable_ceil(v, rule, m, dg, bps, conv, ctx):
    return float(math.ceil(v * (1 + float(m[rule["variable"]]) / 100)))


def _scale_bps(v, rule, m, dg, bps, conv, ctx):
    return v * (conv["bps_per_pct"] + bps) / conv["bps_per_pct"]


def _slsi_recalc(v, rule, m, dg, bps, conv, ctx):
    haircut = rule["base_haircut"] + abs(float(m[rule["haircut_shock_variable"]])) / 100
    liquid = rule["excess_reserve"] + rule["placements"] + rule["sukuk_unencumbered"] * (1 - haircut)
    outflow = rule["net_outflow_30d_base"] + float(m[rule["runoff_variable"]]) / 100 * rule["dpk_base"]
    return liquid / outflow * 100


def _fdr_recalc(v, rule, m, dg, bps, conv, ctx):
    return rule["financing"] / (rule["dpk_base"] * (1 - float(m[rule["variable"]]) / 100)) * 100


def _divide_by_dpk_drop(v, rule, m, dg, bps, conv, ctx):
    return v / (1 - float(m[rule["variable"]]) / 100)


def _additive_variable(v, rule, m, dg, bps, conv, ctx):
    return v + rule["coef"] * float(m[rule["variable"]])


def _max_baseline_variable(v, rule, m, dg, bps, conv, ctx):
    return max(v, float(m[rule["variable"]]))


def _max_baseline_abs_variable(v, rule, m, dg, bps, conv, ctx):
    return max(v, abs(float(m[rule["variable"]])))


def _growth_deviation(v, rule, m, dg, bps, conv, ctx):
    growth = ctx["financing_growth_yoy"] - rule["gdp_coef"] * dg
    return abs(growth - rule["growth_target"])


RULES = {
    "additive": _additive, "multiple_of_delta": _multiple_of_delta, "scale_by_variable": _scale_by_variable,
    "scale_by_variable_ceil": _scale_by_variable_ceil, "scale_bps": _scale_bps, "slsi_recalc": _slsi_recalc,
    "fdr_recalc": _fdr_recalc, "divide_by_dpk_decline": _divide_by_dpk_drop, "additive_variable": _additive_variable,
    "max_baseline_variable": _max_baseline_variable, "max_baseline_abs_variable": _max_baseline_abs_variable,
    "growth_deviation": _growth_deviation,
}


def stressed_values(base: dict[str, float], scenario: str, params: dict, macro: pd.DataFrame,
                    financing_growth_yoy: float) -> dict[str, float]:
    conv = params["conventions"]
    m = macro[scenario]
    dg, bps = _drivers(m, conv)
    out = dict(base)
    ctx = {"base": base, "stressed": out, "financing_growth_yoy": financing_growth_yoy}
    pending = dict(params["transmission"])
    while pending:  # aturan yang merujuk KRI lain dihitung setelah KRI rujukannya
        progressed = False
        for kid, rule in list(pending.items()):
            ref = rule.get("ref_kri")
            if ref and ref in pending:
                continue
            out[kid] = RULES[rule["rule"]](base[kid], rule, m, dg, bps, conv, ctx)
            del pending[kid]
            progressed = True
        if not progressed:
            raise ValueError("dependensi aturan stress melingkar")
    for kid in params["unchanged"]:
        out[kid] = base[kid]
    return out


# ---------- skoring skenario (memakai scoring.py) ----------
def run_stress(kri_monthly: pd.DataFrame, financing_growth_yoy: float, period: str,
               ref: dict[str, pd.DataFrame] | None = None, params: dict | None = None,
               macro: pd.DataFrame | None = None, kpmm_by_scenario: dict[str, float] | None = None) -> dict[str, pd.DataFrame]:
    ref = ref or scoring.load_reference()
    params = params or load_stress_parameters()
    macro = load_macro_scenarios() if macro is None else macro
    ra = ref["risk_appetite"].set_index("kri_id")
    weights = ref["risk_weights"]
    base_rows = kri_monthly[kri_monthly.period == period].set_index("kri_id")
    base = base_rows.value.astype(float).to_dict()

    results, risk_rows, ent_rows = [], [], []
    for s in SCENARIOS:
        sv = stressed_values(base, s, params, macro, financing_growth_yoy)
        if kpmm_by_scenario is not None and "CAP01" in sv:
            sv["CAP01"] = kpmm_by_scenario[s]
        kri_rows = []
        for kid in ra.index:
            r = ra.loc[kid]
            cuts = [r.c1, r.c2, r.c3, r.c4]
            sc = scoring.kri_score(sv[kid], r.direction, cuts)
            kri_rows.append(dict(kri_id=kid, risk_type=r.risk_type, score=sc,
                                 utilization=scoring.utilization(sv[kid], r.direction, r.c4)))
            results.append(dict(scenario=s, kri_id=kid, risk_type=r.risk_type, base_value=base[kid],
                                stressed_value=sv[kid], base_score=int(base_rows.at[kid, "score"]), stressed_score=sc))
        kdf = pd.DataFrame(kri_rows)
        rs = scoring.aggregate_risk(kdf, ref["risk_appetite"], ref["judgment_overrides"], period)  # override dibawa
        rs["scenario"] = s
        risk_rows.append(rs)
        ent = scoring.enterprise_score(rs, weights)
        k = kdf[kdf.risk_type != scoring.CAPITAL_OVERLAY]
        ent_rows.append(dict(scenario=s, enterprise_score=ent, rating=scoring.rating(ent)[0],
                             limit_utilization=scoring.limit_utilization(kdf, ref["risk_appetite"], weights),
                             tolerance_breaches=int((k.score >= 4).sum()), limit_breaches=int((k.score == 5).sum())))

    rs_all = pd.concat(risk_rows, ignore_index=True)
    w = weights.set_index("risk_type").materiality_weight
    base_final = rs_all[rs_all.scenario == "baseline"].set_index("risk_type").final_score
    rs_all["contribution_delta"] = (rs_all.final_score - rs_all.risk_type.map(base_final)) * rs_all.risk_type.map(w)
    order = {r: i for i, r in enumerate(weights.risk_type)}
    rs_all = rs_all.sort_values(["scenario", "risk_type"], key=lambda c: c.map({**{x: i for i, x in enumerate(SCENARIOS)}, **order}),
                                ignore_index=True)
    stress_risk_scores = rs_all[["scenario", "risk_type", "model_score", "final_score", "rating", "contribution_delta"]]
    enterprise = pd.DataFrame(ent_rows)
    return {"stress_results": pd.DataFrame(results), "stress_risk_scores": stress_risk_scores,
            "stress_enterprise_summary": enterprise, "stress_waterfall": waterfall(stress_risk_scores, enterprise)}


def waterfall(stress_risk_scores: pd.DataFrame, enterprise: pd.DataFrame) -> pd.DataFrame:
    """Waterfall baseline → skenario (§5.4): kontribusi = Δ final score × bobot materialitas, diurutkan."""
    rows = []
    base_ent = float(enterprise.set_index("scenario").at["baseline", "enterprise_score"])
    for s in SCENARIOS[1:]:
        g = stress_risk_scores[stress_risk_scores.scenario == s].sort_values("contribution_delta", ascending=False, kind="mergesort")
        end_ent = float(enterprise.set_index("scenario").at[s, "enterprise_score"])
        rows.append(dict(from_scenario="baseline", to_scenario=s, step=0, driver="Enterprise baseline",
                         contribution=base_ent, cumulative=base_ent))
        cum = base_ent
        for i, r in enumerate(g.itertuples(), 1):
            cum += r.contribution_delta
            rows.append(dict(from_scenario="baseline", to_scenario=s, step=i, driver=r.risk_type,
                             contribution=r.contribution_delta, cumulative=cum))
        rows.append(dict(from_scenario="baseline", to_scenario=s, step=len(g) + 1, driver="Floor/eskalasi enterprise",
                         contribution=end_ent - cum, cumulative=end_ent))
        rows.append(dict(from_scenario="baseline", to_scenario=s, step=len(g) + 2, driver=f"Enterprise {s}",
                         contribution=end_ent - base_ent, cumulative=end_ent))
    return pd.DataFrame(rows)
