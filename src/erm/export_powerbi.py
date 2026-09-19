"""Export star schema Power BI (spec §9) → dashboard/model/*.csv.

Dimensi: dim_date, dim_risk, dim_kri, dim_scenario, dim_business_unit.
Fakta : fact_kri_monthly, fact_risk_score, fact_enterprise, fact_stress, fact_capital, fact_actions,
        fact_emerging, fact_interdependency.
Konvensi: skenario "Actual" untuk monitoring bulanan; Baseline/Adverse/Severe untuk stress (tanggal Sep-2026).
File .pbix dirakit manual di Power BI Desktop (lihat dashboard/powerbi_spec.md)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import datastore, scoring

MODEL_DIR = datastore.ROOT / "dashboard" / "model"
COLORS = {"Green": "#2E7D32", "Amber": "#F9A825", "Red": "#C62828"}
SCENARIO_DIM = [(0, "Actual", "Monitoring bulanan (engine)", 0), (1, "Baseline", "Stress baseline", 1),
                (2, "Adverse", "Stress adverse", 2), (3, "Severe", "Stress severe", 3)]
RISK_DEFINITIONS = {
    "Credit": "Kegagalan nasabah/counterparty memenuhi kewajiban akad pembiayaan.",
    "Market": "Perubahan harga pasar (nilai tukar, imbal hasil sukuk) terhadap posisi bank.",
    "Liquidity": "Ketidakmampuan memenuhi kewajiban jatuh tempo dari sumber pendanaan dan aset likuid.",
    "Operational": "Kegagalan proses internal, manusia, sistem, atau kejadian eksternal.",
    "Strategic": "Keputusan atau pelaksanaan strategi yang tidak tepat terhadap perubahan lingkungan bisnis.",
    "Compliance": "Ketidakpatuhan terhadap ketentuan regulasi dan prinsip syariah (opini DPS).",
    "Legal": "Tuntutan hukum dan kelemahan aspek yuridis.",
    "Reputation": "Menurunnya kepercayaan pemangku kepentingan akibat persepsi negatif.",
    "Rate of Return": "Perubahan tingkat imbal hasil yang memengaruhi perilaku deposan (displaced commercial risk).",
    "Investment": "Kerugian atas portofolio investasi/sukuk (penerbit, rating, nilai pasar, durasi).",
}


def date_key(period: str) -> int:
    return int(period.replace("-", ""))


def _period_list(outputs) -> list[str]:
    return sorted(outputs["enterprise_profile_monthly"].period.unique())


def build_model(outputs: dict[str, pd.DataFrame] | None = None, ref: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    outputs = outputs or datastore.load_outputs()
    ref = ref or datastore.load_reference()
    rep = datastore.reporting_period()
    ra, rw = ref["risk_appetite"], ref["risk_weights"]

    # ---------- dimensi ----------
    periods = _period_list(outputs)
    dim_date = pd.DataFrame([dict(date_key=date_key(p), period=p,
                                  month_start=pd.Period(p, freq="M").start_time.strftime("%Y-%m-%d"),
                                  month_end=pd.Period(p, freq="M").end_time.strftime("%Y-%m-%d"),
                                  year=int(p[:4]), month=int(p[5:]), quarter=f"Q{(int(p[5:]) - 1) // 3 + 1}",
                                  month_label=pd.Period(p, freq="M").strftime("%b-%Y"), is_reporting_date=p == rep,
                                  month_index=i + 1) for i, p in enumerate(periods)])
    dim_risk = rw.assign(risk_key=range(1, len(rw) + 1), sort_order=range(1, len(rw) + 1),
                         definition=rw.risk_type.map(RISK_DEFINITIONS))
    dim_risk = pd.concat([dim_risk, pd.DataFrame([dict(risk_key=99, risk_type="Capital Overlay", materiality_weight=0.0,
                                                       measurement_approach="quantitative", depth="Overlay", sort_order=99,
                                                       definition="KPMM sebelum/sesudah stress; bukan bagian 10 risk score.")])],
                         ignore_index=True)
    dim_risk = dim_risk[["risk_key", "risk_type", "materiality_weight", "measurement_approach", "depth", "sort_order", "definition"]]
    risk_key = dim_risk.set_index("risk_type").risk_key

    owners = sorted(set(ra.kri_owner) | set(ref["action_library"].action_owner) | set(ref["emerging_risks"].owner))
    dim_bu = pd.DataFrame(dict(bu_key=range(1, len(owners) + 1), business_unit=owners))
    bu_key = dim_bu.set_index("business_unit").bu_key

    dim_kri = ra.assign(kri_key=range(1, len(ra) + 1), risk_key=ra.risk_type.map(risk_key),
                        bu_key=ra.kri_owner.map(bu_key)).rename(columns={
                            "c1": "cut_strong", "c2": "risk_appetite", "c3": "early_warning_trigger", "c4": "risk_limit"})
    dim_kri = dim_kri[["kri_key", "kri_id", "risk_key", "kri_name", "unit", "direction", "cut_strong", "risk_appetite",
                       "early_warning_trigger", "risk_limit", "kri_weight", "frequency", "measurement_type",
                       "value_start_2025_10", "value_target_2026_09", "target_score", "stress_sensitive", "bu_key"]]
    kri_key = dim_kri.set_index("kri_id").kri_key
    dim_scenario = pd.DataFrame(SCENARIO_DIM, columns=["scenario_key", "scenario", "description", "sort_order"])
    sk = {s.lower(): k for k, s, *_ in SCENARIO_DIM}

    # ---------- fakta ----------
    km = outputs["kri_monthly"]
    fact_kri = km.assign(date_key=km.period.map(date_key), kri_key=km.kri_id.map(kri_key),
                         risk_key=km.risk_type.map(risk_key), color_hex=km.color.map(COLORS),
                         early_warning_flag=km.early_warning_flag.astype(bool))
    fact_kri = fact_kri[["date_key", "kri_key", "risk_key", "value", "score", "zone", "color", "color_hex", "utilization",
                         "trend_label", "early_warning_flag"]]

    rs = outputs["risk_scores_monthly"]
    fr_actual = rs.assign(date_key=rs.period.map(date_key), scenario_key=0, contribution_delta=pd.NA)
    srs = outputs["stress_risk_scores"]
    fr_stress = srs.assign(date_key=date_key(rep), scenario_key=srs.scenario.map(sk),
                           weighted_score=pd.NA, floor_score=pd.NA,
                           override_delta=srs.final_score - srs.model_score,
                           color=srs.final_score.map(lambda s: scoring.rating(s)[1]))
    fact_risk = pd.concat([fr_actual, fr_stress], ignore_index=True)
    fact_risk["risk_key"] = fact_risk.risk_type.map(risk_key)
    fact_risk["final_score_display"] = fact_risk.final_score.map(scoring.r1)
    fact_risk["model_score_display"] = fact_risk.model_score.map(scoring.r1)
    fact_risk["color_hex"] = fact_risk.color.map(COLORS)
    fact_risk = fact_risk[["date_key", "scenario_key", "risk_key", "weighted_score", "floor_score", "model_score",
                           "override_delta", "final_score", "final_score_display", "model_score_display", "rating",
                           "color", "color_hex", "contribution_delta"]]

    ep = outputs["enterprise_profile_monthly"]
    fe_actual = ep.assign(date_key=ep.period.map(date_key), scenario_key=0)
    se = outputs["stress_enterprise_summary"]
    fe_stress = se.assign(date_key=date_key(rep), scenario_key=se.scenario.map(sk),
                          emerging_count=int(ep.emerging_count.iloc[-1]))
    fact_ent = pd.concat([fe_actual, fe_stress], ignore_index=True)
    fact_ent["enterprise_score_display"] = fact_ent.enterprise_score.map(scoring.r1)
    fact_ent["color_hex"] = fact_ent.enterprise_score.map(lambda s: COLORS[scoring.rating(s)[1]])
    fact_ent = fact_ent[["date_key", "scenario_key", "enterprise_score", "enterprise_score_display", "rating", "color_hex",
                         "limit_utilization", "tolerance_breaches", "limit_breaches", "emerging_count"]]

    st = outputs["stress_results"]
    fact_stress = st.assign(date_key=date_key(rep), scenario_key=st.scenario.map(sk), kri_key=st.kri_id.map(kri_key),
                            risk_key=st.risk_type.map(risk_key), score_delta=st.stressed_score - st.base_score)
    fact_stress = fact_stress[["date_key", "scenario_key", "kri_key", "risk_key", "base_value", "stressed_value",
                               "base_score", "stressed_score", "score_delta"]]

    cap = outputs["capital_overlay"]
    fact_capital = cap.assign(date_key=date_key(rep), scenario_key=cap.scenario.map(sk)).drop(columns="scenario")
    fact_capital = fact_capital[["date_key", "scenario_key"] + [c for c in cap.columns if c != "scenario"]]

    act = outputs["management_actions"]
    rep_date = pd.Timestamp(datastore.load_config()["bank_profile"]["reporting"]["reporting_date"])
    fact_actions = act.assign(date_key=act.period.map(date_key), kri_key=act.kri_id.map(kri_key),
                              risk_key=act.risk_type.map(risk_key), bu_key=act.owner.map(bu_key),
                              is_overdue=act.status == "Overdue",
                              days_to_due=(pd.to_datetime(act.due_date) - rep_date).dt.days)
    fact_actions = fact_actions[["action_id", "date_key", "risk_key", "kri_key", "bu_key", "finding", "severity",
                                 "recommended_action", "due_date", "status", "is_overdue", "days_to_due", "trigger_rule"]]

    er = ref["emerging_risks"]
    fact_emerging = er.assign(date_key=date_key(rep), bu_key=er.owner.map(bu_key),
                              primary_risk_key=er.linked_risk_types.str.split(";").str[0].map(risk_key))
    fact_emerging = fact_emerging.drop(columns="owner")

    ed = ref["interdependency_edges"]
    fact_inter = ed.assign(edge_key=range(1, len(ed) + 1), source_risk_key=ed.source.map(risk_key).astype("Int64"),
                           target_risk_key=ed.target.map(risk_key).astype("Int64"),
                           source_type=ed.source.map(lambda s: "risk" if s in risk_key.index else "macro driver"))
    fact_inter = fact_inter[["edge_key", "source", "target", "source_type", "source_risk_key", "target_risk_key",
                             "channel", "strength", "evidence"]]

    return {"dim_date": dim_date, "dim_risk": dim_risk, "dim_kri": dim_kri, "dim_scenario": dim_scenario,
            "dim_business_unit": dim_bu, "fact_kri_monthly": fact_kri, "fact_risk_score": fact_risk,
            "fact_enterprise": fact_ent, "fact_stress": fact_stress, "fact_capital": fact_capital,
            "fact_actions": fact_actions, "fact_emerging": fact_emerging, "fact_interdependency": fact_inter}


def export(model_dir: Path | str = MODEL_DIR, outputs=None, ref=None) -> list[Path]:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, df in build_model(outputs, ref).items():
        p = model_dir / f"{name}.csv"
        df.to_csv(p, index=False, lineterminator="\n", encoding="utf-8")
        paths.append(p)
    return paths
