"""Fase 3 — KRI engine dan risk appetite: §12 no. 3, no. 9, regresi baseline vs reference_output.txt,
dan tabel Enterprise Risk Profile Sep-2026 vs ringkasan spec §4."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from erm import scoring
from erm.__main__ import run_engine
from erm.generator import generate_all

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
SEP = "2026-09"
COLOR = {"🟢": "Green", "🟡": "Amber", "🔴": "Red"}

SPEC_OUTPUT_COLUMNS = {  # spec §8.4
    "kri_monthly": ["period", "kri_id", "risk_type", "value", "score", "zone", "color", "utilization",
                    "trend_label", "early_warning_flag"],
    "risk_scores_monthly": ["period", "risk_type", "weighted_score", "floor_score", "model_score", "override_delta",
                            "final_score", "rating", "color"],
    "enterprise_profile_monthly": ["period", "enterprise_score", "rating", "limit_utilization", "tolerance_breaches",
                                   "limit_breaches", "emerging_count"],
}


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    out = tmp_path_factory.mktemp("output")
    generate_all(raw)
    run_engine(raw, out)
    return {name: pd.read_csv(out / f"{name}.csv") for name in SPEC_OUTPUT_COLUMNS}


@pytest.fixture(scope="module")
def ra():
    return pd.read_csv(REF / "risk_appetite.csv")


# ---------- unit: §3.1–3.6 ----------
@pytest.mark.parametrize("x,d,cuts,expected", [
    (2.5, "lower", [2.0, 2.5, 3.0, 3.5], 2), (2.5000001, "lower", [2.0, 2.5, 3.0, 3.5], 3),
    (3.6, "lower", [2.0, 2.5, 3.0, 3.5], 5), (110, "higher", [125, 110, 105, 100], 2),
    (109.99, "higher", [125, 110, 105, 100], 3), (99, "higher", [125, 110, 105, 100], 5),
    (-8.5, "lower", [5, 10, 15, 20], 2),
])
def test_kri_score_cutpoints(x, d, cuts, expected):
    assert scoring.kri_score(x, d, cuts) == expected


def test_r1_round_half_up_and_rating():
    assert scoring.r1(2.65) == 2.7 and scoring.r1(2.25) == 2.3 and scoring.r1(2.9545) == 3.0
    assert scoring.rating(1.44)[0] == "Low" and scoring.rating(1.45)[0] == "Low to Moderate"
    assert scoring.rating(2.45) == ("Moderate", "Amber")
    assert scoring.rating(3.45) == ("Moderate to High", "Red") and scoring.rating(4.45) == ("High", "Red")


def test_floor_rule_market_adverse_example(ra):
    scores = pd.DataFrame({"kri_id": ["MR01", "MR02", "MR03"], "score": [2, 5, 2]})
    rs = scoring.aggregate_risk(scores, ra, pd.read_csv(REF / "judgment_overrides.csv"), "2026-09")
    r = rs.iloc[0]
    assert r.weighted_score == pytest.approx(2.9) and r.model_score == pytest.approx(3.5)


def test_override_only_within_validity_and_capped():
    ov = pd.read_csv(REF / "judgment_overrides.csv")
    assert scoring.override_delta(ov, "Compliance", "2026-09") == pytest.approx(0.3)
    assert scoring.override_delta(ov, "Compliance", "2026-08") == 0.0
    assert scoring.override_delta(ov, "Credit", "2026-09") == 0.0
    bad = ov.assign(final_score=4.5)
    with pytest.raises(ValueError):
        scoring.override_delta(bad, "Compliance", "2026-09")


def test_enterprise_floor_and_escalation():
    w = pd.read_csv(REF / "risk_weights.csv")
    rs = pd.DataFrame({"risk_type": w.risk_type, "final_score": 2.0})
    rs.loc[rs.risk_type == "Liquidity", "final_score"] = 4.6   # bobot 0,15 ≥ 0,10
    assert scoring.enterprise_score(rs, w) == pytest.approx(3.5)
    rs.loc[rs.risk_type == "Liquidity", "final_score"] = 2.0
    rs.loc[rs.risk_type == "Legal", "final_score"] = 5.0       # bobot 0,04: hanya floor max − 1,5
    assert scoring.enterprise_score(rs, w) == pytest.approx(3.5)
    rs.loc[rs.risk_type == "Legal", "final_score"] = 4.6
    assert scoring.enterprise_score(rs, w) == pytest.approx(3.1)


def test_utilization_cap():
    assert scoring.utilization(30, "lower", 20) == 1.5
    assert scoring.utilization(116, "higher", 100) == pytest.approx(100 / 116)


def test_trend_and_early_warning_synthetic():
    assert scoring.trend_label(np.array([1, 1, 1, 3, 3, 3.0]), "lower", 0, 10) == "Deteriorating"
    assert scoring.trend_label(np.array([1, 1, 1, 3, 3, 3.0]), "higher", 0, 10) == "Improving"
    assert scoring.trend_label(np.array([1, 1, 1, 1.5, 1.5, 1.5]), "lower", 0, 10) == "Stable"
    assert scoring.trend_label(np.array([1, 2.0]), "lower", 0, 10) == "Insufficient history"
    rising = np.array([0, 0, 0, 1.0, 3.3, 4.5])
    assert scoring.early_warning(rising, 3, "lower", [2, 4, 6, 8]) is True
    assert scoring.early_warning(np.full(6, 4.5), 3, "lower", [2, 4, 6, 8]) is False
    assert scoring.early_warning(rising, 4, "lower", [2, 4, 6, 8]) is False


# ---------- struktur output ----------
def test_output_columns_and_grain(engine, ra):
    for name, cols in SPEC_OUTPUT_COLUMNS.items():
        assert list(engine[name].columns) == cols, name
    k = engine["kri_monthly"]
    assert k.groupby("period").size().eq(43).all() and k.period.nunique() == 12
    assert set(k.kri_id) == set(ra.kri_id)
    assert engine["risk_scores_monthly"].groupby("period").size().eq(10).all()


# ---------- §12 no. 3 ----------
def test_baseline_scores_match_target_score(engine, ra):
    sep = engine["kri_monthly"].query("period == @SEP").set_index("kri_id")
    t = ra.set_index("kri_id").target_score
    assert (sep.score.reindex(t.index) == t).all(), sep.score[sep.score.reindex(t.index) != t]
    assert len(ra[ra.risk_type != "Capital Overlay"]) == 42


# ---------- §12 no. 9 ----------
def test_storyline_trend_and_early_warning(engine):
    sep = engine["kri_monthly"].query("period == @SEP").set_index("kri_id")
    for kid in ["LQ01", "LQ04", "OR01", "OR04"]:
        assert sep.at[kid, "trend_label"] == "Deteriorating", kid
    assert sep.early_warning_flag.astype(bool).sum() >= 1
    assert (sep.loc[sep.early_warning_flag.astype(bool), "score"] <= 3).all()


# ---------- regresi baseline vs reference_output.txt ----------
def parse_reference_block(name: str) -> tuple[dict, dict]:
    text = (REF / "reference_output.txt").read_text(encoding="utf-8")
    block = text.split(f"=== {name.upper()} ===")[1].split("===")[0]
    risks = {}
    for m in re.finditer(r"^(.+?)\s+wavg=([\d.]+) model=([\d.]+) final=([\d.]+) \('(.+?)', '(\w+)'\)", block, re.M):
        risks[m.group(1).strip()] = dict(wavg=float(m.group(2)), model=float(m.group(3)), final=float(m.group(4)),
                                         rating=m.group(5), color=m.group(6))
    e = re.search(r"ENTERPRISE ([\d.]+) \('(.+?)', '(\w+)'\) \| KRI score>=4: (\d+) \| score 5: (\d+) \| RAU (\d+)%", block)
    ent = dict(score=float(e.group(1)), rating=e.group(2), color=e.group(3), breaches=int(e.group(4)),
               limit=int(e.group(5)), rau=int(e.group(6)))
    return risks, ent


def test_regression_baseline_vs_reference_output(engine):
    ref_risks, ref_ent = parse_reference_block("baseline")
    assert len(ref_risks) == 10
    rs = engine["risk_scores_monthly"].query("period == @SEP").set_index("risk_type")
    for risk, exp in ref_risks.items():
        r = rs.loc[risk]
        assert scoring.r1(r.weighted_score) == exp["wavg"], risk
        assert scoring.r1(r.model_score) == exp["model"], risk
        assert scoring.r1(r.final_score) == exp["final"], risk
        assert abs(r.final_score - exp["final"]) <= 0.05 + 1e-9, risk
        assert (r.rating, r.color) == (exp["rating"], exp["color"]), risk
    e = engine["enterprise_profile_monthly"].query("period == @SEP").iloc[0]
    assert scoring.r1(e.enterprise_score) == ref_ent["score"]
    assert abs(e.enterprise_score - ref_ent["score"]) <= 0.05
    assert e.rating == ref_ent["rating"]
    assert (e.tolerance_breaches, e.limit_breaches) == (ref_ent["breaches"], ref_ent["limit"])
    assert round(e.limit_utilization) == ref_ent["rau"]


# ---------- acceptance: ringkasan Enterprise Risk Profile spec §4 ----------
def parse_spec_profile() -> list[dict]:
    text = (REF / "ERM_Blueprint_v3_Spec.md").read_text(encoding="utf-8")
    sec = text.split("### Ringkasan Enterprise Risk Profile")[1].split("Hero metrics")[0]
    rows = []
    for line in sec.splitlines():
        m = re.match(r"^\|\s*\**([A-Za-z ]+?)\**\s*\|\s*\**([\d,]+)(?:\s*\(model ([\d,]+)\))?(?:\s*—\s*([A-Za-z ]+))?\**\s*\|\s*(\S+)\s*\|", line)
        if m and m.group(1) not in ("Risk",):
            rows.append(dict(risk=m.group(1).strip(), score=float(m.group(2).replace(",", ".")),
                             model=float(m.group(3).replace(",", ".")) if m.group(3) else None,
                             rating=m.group(4).strip() if m.group(4) else None, color=COLOR[m.group(5)]))
    return rows


def test_enterprise_risk_profile_sep_2026_identical_to_spec(engine):
    spec = parse_spec_profile()
    assert len(spec) == 11
    table = scoring.profile_table(engine["risk_scores_monthly"], engine["enterprise_profile_monthly"], SEP).set_index("risk")
    assert list(table.index) == [r["risk"] for r in spec]
    for r in spec:
        row = table.loc[r["risk"]]
        assert row.score == r["score"], r["risk"]
        assert row.color == r["color"], r["risk"]
        if r["model"] is not None:
            assert row.model == r["model"], r["risk"]
        else:
            assert pd.isna(row.model), r["risk"]
        if r["rating"]:
            assert row.rating == r["rating"]


def test_hero_metrics_match_spec(engine):
    text = (REF / "ERM_Blueprint_v3_Spec.md").read_text(encoding="utf-8")
    m = re.search(r"Limit Utilization \*\*(\d+)%\*\* · Tolerance breach \*\*(\d+) KRI\*\* · Limit breach \*\*(\d+)\*\* · "
                  r"Emerging risk \(register\) \*\*(\d+)\*\*", text)
    e = engine["enterprise_profile_monthly"].query("period == @SEP").iloc[0]
    assert (round(e.limit_utilization), e.tolerance_breaches, e.limit_breaches, e.emerging_count) == tuple(map(int, m.groups()))


def test_engine_outputs_reproducible(tmp_path, engine):
    raw, out = tmp_path / "raw", tmp_path / "out"
    generate_all(raw)
    run_engine(raw, out)
    for name, df in engine.items():
        pd.testing.assert_frame_equal(pd.read_csv(out / f"{name}.csv"), df)
