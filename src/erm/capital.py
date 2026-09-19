"""Capital Adequacy Overlay — KPMM sebelum/sesudah stress (spec §5.5).

Bukan bagian dari 10 risk score. Loss rate kredit adalah asumsi tunggal, BUKAN model kerugian kredit.
Konservatif: laba berjalan tidak diperhitungkan."""
from __future__ import annotations

import pandas as pd

from . import scoring
from .stress import SCENARIOS, load_macro_scenarios, load_stress_parameters


def capital_overlay(stress_results: pd.DataFrame | None = None, params: dict | None = None,
                    macro: pd.DataFrame | None = None, ref: dict | None = None,
                    delta_npf: dict[str, float] | None = None) -> pd.DataFrame:
    """ΔNPF diambil dari stress_results (CR01 stressed − base) atau argumen `delta_npf` (pp)."""
    params = params or load_stress_parameters()
    macro = load_macro_scenarios() if macro is None else macro
    ref = ref or scoring.load_reference()
    c = params["capital_overlay"]
    cap = ref["risk_appetite"].set_index("kri_id").loc[c["cap01_kri_id"]]
    rows = []
    for s in SCENARIOS:
        m = macro[s]
        if delta_npf is not None:
            dnpf = delta_npf[s]
        else:
            r = stress_results[(stress_results.scenario == s) & (stress_results.kri_id == c["credit_loss"]["delta_npf_from"])].iloc[0]
            dnpf = r.stressed_value - r.base_value
        bps = float(m["policy_rate_shift"])
        credit = dnpf / 100 * c["credit_loss"]["financing"] * c["credit_loss"]["loss_rate"]
        invest = c["investment_loss"]["fvoci_portfolio"] * abs(float(m[c["investment_loss"]["shock_variable"]])) / 100
        op = c["operational_loss"]["annual_loss_base"] * float(m[c["operational_loss"]["uplift_variable"]]) / 100
        dcr = c["dcr_cost"]["deposito_mudharabah"] * bps / 10000 * c["dcr_cost"]["pass_through"]
        total = credit + invest + op + dcr
        capital = c["capital"]["capital_base"] - total
        atmr = c["atmr"]["atmr_base"] * (1 + float(m[c["atmr"]["uplift_variable"]]) / 100)
        kpmm = capital / atmr * 100
        rows.append(dict(scenario=s, credit_loss=credit, investment_loss=invest, op_loss=op, dcr_cost=dcr,
                         total_loss=total, capital=capital, atmr=atmr, kpmm=kpmm,
                         cap_score=scoring.kri_score(kpmm, cap.direction, [cap.c1, cap.c2, cap.c3, cap.c4])))
    return pd.DataFrame(rows)
