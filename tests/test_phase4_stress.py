"""Fase 4 — stress testing, capital overlay, management action.
§12 no. 4 (regresi 3 skenario), no. 5 (monotonic), no. 8 (scope guard); reproduksi tabel §5.3, §5.4, §5.5."""
import ast
import re
from pathlib import Path

import pandas as pd
import pytest

from erm import capital, scoring, stress
from erm.__main__ import run_engine
from erm.generator import generate_all

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
SPEC = (REF / "ERM_Blueprint_v3_Spec.md").read_text(encoding="utf-8")
SCORE_TOL = 0.05 + 1e-9
KPMM_TOL = 0.1 + 1e-9
SCEN = ["baseline", "adverse", "severe"]

OUTPUT_COLUMNS = {  # spec §8.4
    "stress_results": ["scenario", "kri_id", "risk_type", "base_value", "stressed_value", "base_score", "stressed_score"],
    "stress_risk_scores": ["scenario", "risk_type", "model_score", "final_score", "rating", "contribution_delta"],
    "capital_overlay": ["scenario", "credit_loss", "investment_loss", "op_loss", "dcr_cost", "total_loss", "capital",
                        "atmr", "kpmm", "cap_score"],
    "management_actions": ["action_id", "period", "risk_type", "kri_id", "finding", "severity", "recommended_action",
                           "owner", "due_date", "status", "trigger_rule"],
}


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    raw, o = tmp_path_factory.mktemp("raw"), tmp_path_factory.mktemp("out")
    generate_all(raw)
    run_engine(raw, o)
    return {p.stem: pd.read_csv(p) for p in o.glob("*.csv")}


def num(s: str) -> float:
    return float(s.replace("−", "-").replace(".", "").replace(",", ".")) if re.search(r"\d\.\d{3}", s) else float(s.replace("−", "-").replace(",", "."))


def final_table(out):
    return out["stress_risk_scores"].pivot(index="risk_type", columns="scenario", values="final_score")


def ent_table(out):
    return out["stress_enterprise_summary"].set_index("scenario")


# ---------- struktur ----------
def test_output_columns(out):
    for name, cols in OUTPUT_COLUMNS.items():
        assert list(out[name].columns) == cols, name
    assert {"stress_enterprise_summary", "stress_waterfall"} <= set(out)


def test_stress_uses_engine_sep_values_not_targets(out):
    sep = out["kri_monthly"].query("period == '2026-09'").set_index("kri_id").value
    base = out["stress_results"].query("scenario == 'baseline'").set_index("kri_id").base_value
    assert (base.reindex(sep.index) - sep).abs().max() < 1e-9


def test_stress_module_reuses_scoring_without_duplication():
    tree = ast.parse((ROOT / "src" / "erm" / "stress.py").read_text(encoding="utf-8"))
    defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    scoring_defs = {n.name for n in ast.walk(ast.parse((ROOT / "src" / "erm" / "scoring.py").read_text(encoding="utf-8")))
                    if isinstance(n, ast.FunctionDef)}
    assert not (defs & scoring_defs)
    src = (ROOT / "src" / "erm" / "stress.py").read_text(encoding="utf-8")
    for fn in ["scoring.kri_score", "scoring.aggregate_risk", "scoring.enterprise_score", "scoring.limit_utilization"]:
        assert fn in src


def test_override_delta_carried_to_all_scenarios(out):
    c = out["stress_risk_scores"].query("risk_type == 'Compliance'")
    assert ((c.final_score - c.model_score) - 0.3).abs().max() < 1e-9 and len(c) == 3


def test_stress_rules_unit_examples():
    params, macro = stress.load_stress_parameters(), stress.load_macro_scenarios()
    ra = pd.read_csv(REF / "risk_appetite.csv").set_index("kri_id")
    base = ra.value_target_2026_09.to_dict()
    sv = stress.stressed_values(base, "severe", params, macro, financing_growth_yoy=22.0)
    assert sv["CR01"] == pytest.approx(4.25) and sv["CR02"] == pytest.approx(5.3 + 1.5 * 1.45)
    assert sv["LQ01"] == pytest.approx(89.30, abs=0.01) and sv["LQ02"] == pytest.approx(97.06, abs=0.01)
    assert sv["OR02"] == 5.0 and sv["ST01"] == pytest.approx(5.0) and sv["RR03"] == pytest.approx(3.775)
    assert sv["IV03"] == 15.0 and sv["LQ05"] == 12.0 and sv["MR02"] == pytest.approx(7.35)
    for kid in params["unchanged"]:
        assert sv[kid] == base[kid]


# ---------- §12 no. 4: regresi vs reference_output.txt ----------
def parse_reference():
    text = (REF / "reference_output.txt").read_text(encoding="utf-8")
    res = {}
    for s in SCEN:
        block = text.split(f"=== {s.upper()} ===")[1].split("===")[0].split("\nCAP ")[0]
        risks = {m.group(1).strip(): (float(m.group(2)), m.group(3)) for m in
                 re.finditer(r"^(.+?)\s+wavg=[\d.]+ model=[\d.]+ final=([\d.]+) \('(.+?)',", block, re.M)}
        e = re.search(r"ENTERPRISE ([\d.]+) \('(.+?)', '\w+'\) \| KRI score>=4: (\d+) \| score 5: (\d+) \| RAU (\d+)%", block)
        res[s] = dict(risks=risks, ent=float(e.group(1)), rating=e.group(2), b4=int(e.group(3)), b5=int(e.group(4)), rau=int(e.group(5)))
    caps = {m.group(1): dict(credit=int(m.group(2)), inv=int(m.group(3)), op=int(m.group(4)), dcr=int(m.group(5)),
                             total=int(m.group(6)), capital=int(m.group(7)), atmr=int(m.group(8)), kpmm=float(m.group(9)))
            for m in re.finditer(r"CAP (\w+): credit (\d+) inv (\d+) op (\d+) ror (\d+) total (\d+) -> modal (\d+) ATMR (\d+) KPMM ([\d.]+)%", text)}
    return res, caps


@pytest.mark.parametrize("scenario", SCEN)
def test_regression_scores_enterprise_rau_breaches(out, scenario):
    ref, _ = parse_reference()
    r = ref[scenario]
    ft = final_table(out)[scenario]
    rs = out["stress_risk_scores"].query("scenario == @scenario").set_index("risk_type")
    assert len(r["risks"]) == 10
    for risk, (final, rating_label) in r["risks"].items():
        assert abs(ft[risk] - final) <= SCORE_TOL, (risk, ft[risk], final)
        assert rs.at[risk, "rating"] == rating_label, risk
    e = ent_table(out).loc[scenario]
    assert abs(e.enterprise_score - r["ent"]) <= SCORE_TOL and scoring.r1(e.enterprise_score) == r["ent"]
    assert e.rating == r["rating"]
    assert (e.tolerance_breaches, e.limit_breaches) == (r["b4"], r["b5"])
    assert round(e.limit_utilization) == r["rau"]


@pytest.mark.parametrize("scenario", ["adverse", "severe"])
def test_regression_capital_overlay(out, scenario):
    _, caps = parse_reference()
    c = out["capital_overlay"].set_index("scenario").loc[scenario]
    exp = caps[scenario]
    assert (round(c.credit_loss), round(c.investment_loss), round(c.op_loss), round(c.dcr_cost), round(c.total_loss)) == \
           (exp["credit"], exp["inv"], exp["op"], exp["dcr"], exp["total"])
    assert (round(c.capital), round(c.atmr)) == (exp["capital"], exp["atmr"])
    assert abs(c.kpmm - exp["kpmm"]) <= KPMM_TOL


# ---------- acceptance: tabel §5.3 ----------
def test_table_5_3_reproduced(out):
    sec = SPEC.split("### 5.3")[1].split("### 5.4")[0]
    ft, et = final_table(out), ent_table(out)
    n = 0
    for line in sec.splitlines():
        cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[1] or not re.match(r"[\d−]", cells[1]):
            continue
        label = cells[0]
        if label in ft.index:
            for s, cell in zip(SCEN, cells[1:]):
                assert abs(scoring.r1(ft.at[label, s]) - num(cell)) <= SCORE_TOL, (label, s)
                assert abs(ft.at[label, s] - num(cell)) <= SCORE_TOL, (label, s)
            n += 1
        elif label == "Enterprise":
            for s, cell in zip(SCEN, cells[1:]):
                score, rating_label = re.match(r"([\d,]+) (.+)", cell).groups()
                assert scoring.r1(et.at[s, "enterprise_score"]) == num(score) and et.at[s, "rating"] == rating_label
            n += 1
        elif label == "Limit Utilization":
            for s, cell in zip(SCEN, cells[1:]):
                assert round(et.at[s, "limit_utilization"]) == int(cell.rstrip("%"))
            n += 1
        elif label.startswith("KRI skor"):
            for s, cell in zip(SCEN, cells[1:]):
                b4, b5 = (int(x) for x in cell.split("/"))
                assert (et.at[s, "tolerance_breaches"], et.at[s, "limit_breaches"]) == (b4, b5)
            n += 1
    assert n == 13


def test_example_stressed_kri_values_5_3(out):
    sr = out["stress_results"].pivot(index="kri_id", columns="scenario", values="stressed_value")
    exp = {"LQ01": (116, 106, 89), "LQ02": (85.4, 89.9, 97.1), "CR01": (2.8, 3.5, 4.25), "RR03": (4.4, 4.15, 3.78)}
    for kid, vals in exp.items():
        for s, v in zip(SCEN, vals):
            decimals = len(str(v).split(".")[1]) if "." in str(v) else 0
            assert abs(sr.at[kid, s] - v) <= 0.5 * 10 ** -decimals + 1e-9, (kid, s, sr.at[kid, s])


# ---------- acceptance: waterfall §5.4 ----------
def test_waterfall_5_4_reproduced(out):
    sec = SPEC.split("### 5.4")[1].split("### 5.5")[0]
    spec_rows = {m.group(1): float(m.group(2).replace(",", ".")) for m in
                 re.finditer(r"^\| ([A-Za-z ]+) \| \+([\d,]+) \|", sec, re.M)}
    assert len(spec_rows) == 8
    w = out["stress_waterfall"].query("to_scenario == 'severe'").set_index("driver")
    weights = pd.read_csv(REF / "risk_weights.csv").set_index("risk_type").materiality_weight
    for driver, contrib in spec_rows.items():
        tol = SCORE_TOL * weights[driver] + 0.005   # toleransi skor ±0,05 × bobot + pembulatan tampilan 2 desimal
        assert abs(w.at[driver, "contribution"] - contrib) <= tol, (driver, w.at[driver, "contribution"], contrib)
    drivers = w[w.step.between(1, 10) & (w.contribution > 0)].index.tolist()
    assert drivers[:2] == ["Liquidity", "Credit"]
    total = w.loc["Enterprise severe", "contribution"]
    assert abs(total - 1.0) <= SCORE_TOL
    assert w.loc["Enterprise severe", "cumulative"] == pytest.approx(ent_table(out).at["severe", "enterprise_score"])


# ---------- acceptance: tabel §5.5 ----------
def test_table_5_5_reproduced(out):
    c = out["capital_overlay"].set_index("scenario")
    exp = {"credit_loss": (0, 129, 268), "investment_loss": (0, 300, 900), "op_loss": (0, 18, 45),
           "dcr_cost": (0, 120, 300), "total_loss": (0, 567, 1513), "capital": (7000, 6433, 5487),
           "atmr": (40000, 40800, 42000)}
    for col, vals in exp.items():
        assert tuple(int(round(c.at[s, col])) for s in SCEN) == vals, col
    assert tuple(round(c.at[s, "kpmm"], 1) for s in SCEN) == (17.5, 15.8, 13.1)
    assert tuple(int(c.at[s, "cap_score"]) for s in SCEN) == (1, 2, 3)
    sev = c.loc["severe"]
    assert sev.investment_loss / sev.total_loss == pytest.approx(0.60, abs=0.01)   # insight: sukuk 60% erosi modal
    cap = out["stress_results"].query("kri_id == 'CAP01'").set_index("scenario")
    assert (cap.stressed_value - c.kpmm).abs().max() < 1e-9


# ---------- §12 no. 5: monotonic ----------
def test_monotonic_risk_scores(out):
    ft = final_table(out)
    for risk, row in ft.iterrows():
        assert row["severe"] + 1e-9 >= row["adverse"] >= row["baseline"] - 1e-9, risk
    e = ent_table(out).enterprise_score
    assert e["severe"] >= e["adverse"] >= e["baseline"]


def test_monotonic_kri_scores_except_documented(out):
    sr = out["stress_results"].pivot(index="kri_id", columns="scenario", values="stressed_score")
    violating = {k for k, r in sr.iterrows() if not (r["severe"] >= r["adverse"] >= r["baseline"])}
    assert violating <= stress.MAY_IMPROVE, violating
    # ST01 terdokumentasi dapat membaik: growth melambat → deviasi terhadap target mengecil
    assert sr.at["ST01", "adverse"] < sr.at["ST01", "baseline"]


# ---------- §12 no. 8: scope guard ----------
BANNED = ["ecl", "ckpn", "pd_model", "lgd", "var_", "monte_carlo", "sklearn"]


def test_scope_guard_file_and_function_names():
    offenders = []
    for path in ROOT.rglob("*"):
        if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
            continue
        if any(b in path.name.lower() for b in BANNED):
            offenders.append(str(path))
        if path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if any(b in node.name.lower() for b in BANNED):
                        offenders.append(f"{path}:{node.name}")
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] + ([node.module] if getattr(node, "module", None) else [])
                    if any("sklearn" in (m or "") for m in mods):
                        offenders.append(f"{path}:import sklearn")
    assert not offenders, offenders


# ---------- management actions (§8.4) ----------
def test_management_actions_follow_rules(out):
    a = out["management_actions"]
    lib = pd.read_csv(REF / "action_library.csv").set_index("kri_id")
    km = out["kri_monthly"].set_index(["period", "kri_id"])
    assert len(a) > 0 and a.action_id.is_unique
    for r in a.itertuples():
        sc = km.at[(r.period, r.kri_id), "score"]
        assert sc >= 4
        assert r.recommended_action == lib.at[r.kri_id, "recommended_action"]
        assert r.owner == lib.at[r.kri_id, "action_owner"]
        days = (pd.Timestamp(r.due_date) - pd.Period(r.period, freq="M").end_time.normalize()).days
        assert days == (14 if sc == 5 else 30)
        if sc == 5:
            assert "eskalasi Direksi" in r.trigger_rule
    sep = out["kri_monthly"].query("period == '2026-09' and score >= 4 and risk_type != 'Capital Overlay'")
    live = a[a.status.isin(["Open", "Overdue"])]
    assert set(sep.kri_id) == set(live.kri_id)
    assert set(a.status) <= {"Open", "Overdue", "Closed", "Superseded (eskalasi skor 5)"}
