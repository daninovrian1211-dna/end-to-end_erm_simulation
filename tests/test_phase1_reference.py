"""Fase 1 — integritas reference data dan konfigurasi terhadap ERM_Blueprint_v3_Spec.md."""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
CFG = ROOT / "config"
SPEC = REF / "ERM_Blueprint_v3_Spec.md"
TOL = 1e-9
RISK_TYPES = ["Credit", "Market", "Liquidity", "Operational", "Strategic",
              "Compliance", "Legal", "Reputation", "Rate of Return", "Investment"]


@pytest.fixture(scope="module")
def ra():
    return pd.read_csv(REF / "risk_appetite.csv")


@pytest.fixture(scope="module")
def stress_cfg():
    return yaml.safe_load((CFG / "stress_parameters.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def profile():
    return yaml.safe_load((CFG / "bank_profile.yaml").read_text(encoding="utf-8"))


def spec_kri_rows():
    """Baris tabel KRI di spec §4: | ID | nama | arah | cut-point | bobot | awal → target | skor |"""
    text = SPEC.read_text(encoding="utf-8")
    sec4 = text.split("## 4. KRI catalogue")[1].split("## 5. Enterprise stress testing")[0]
    rows = {}
    for line in sec4.splitlines():
        m = re.match(r"^\|\s*([A-Z]{2}\d{2})\s*\|", line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows[m.group(1)] = cells
    return rows


def num(s):
    return float(s.replace(",", "."))


# ---------- read-only reference ----------
def test_reference_checksums_unchanged():
    for line in (REF / "CHECKSUMS.sha256").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        assert hashlib.sha256((REF / name.strip()).read_bytes()).hexdigest() == digest, name


def test_reference_calc_reproduces_reference_output():
    out = subprocess.run([sys.executable, "reference_calc.py"], cwd=REF,
                         capture_output=True, text=True, check=True).stdout
    norm = lambda s: [l.rstrip() for l in s.strip().splitlines()]
    assert norm(out) == norm((REF / "reference_output.txt").read_text())


# ---------- bobot (spec §12 #6) ----------
def test_kri_weights_sum_to_one_per_risk(ra):
    sums = ra[ra.risk_type != "Capital Overlay"].groupby("risk_type").kri_weight.sum()
    assert sorted(sums.index) == sorted(RISK_TYPES)
    for risk, s in sums.items():
        assert s == pytest.approx(1.0, abs=TOL), risk


def test_materiality_weights_sum_to_one():
    w = pd.read_csv(REF / "risk_weights.csv")
    assert sorted(w.risk_type) == sorted(RISK_TYPES)
    assert w.materiality_weight.sum() == pytest.approx(1.0, abs=TOL)


def test_materiality_weights_match_spec():
    expected = {"Credit": .25, "Liquidity": .15, "Operational": .12, "Rate of Return": .10,
                "Strategic": .08, "Compliance": .08, "Reputation": .06, "Market": .05,
                "Legal": .04, "Investment": .07}
    w = pd.read_csv(REF / "risk_weights.csv").set_index("risk_type").materiality_weight
    assert w.to_dict() == pytest.approx(expected)


# ---------- katalog KRI (spec §4) ----------
def test_all_spec_kris_present_in_csv(ra):
    spec_ids = set(spec_kri_rows())
    csv_ids = set(ra.kri_id) - {"CAP01"}
    assert spec_ids, "tabel KRI spec §4 tidak terbaca"
    assert spec_ids == csv_ids


def test_csv_matches_spec_cutpoints_weights_targets(ra):
    r = ra.set_index("kri_id")
    for kid, cells in spec_kri_rows().items():
        _, _, direction, cuts, weight, values, score = cells
        row = r.loc[kid]
        assert row.direction == direction, kid
        assert [num(c) for c in cuts.split("/")] == pytest.approx([row.c1, row.c2, row.c3, row.c4]), kid
        assert num(weight) == pytest.approx(row.kri_weight), kid
        start, target = [v.strip() for v in values.split("→")]
        assert num(start) == pytest.approx(row.value_start_2025_10), kid
        assert num(target.split()[0]) == pytest.approx(row.value_target_2026_09), kid
        assert int(score) == row.target_score, kid


def test_capital_overlay_row(ra):
    cap = ra.set_index("kri_id").loc["CAP01"]
    assert [cap.c1, cap.c2, cap.c3, cap.c4] == [16, 14, 12, 10.5]
    assert cap.direction == "higher" and cap.kri_weight == 0


# ---------- stress_parameters.yaml (spec §5.2, §5.5) ----------
SENSITIVE = ["CR01", "CR02", "CR03", "MR01", "MR02", "LQ01", "LQ02", "LQ03", "LQ04", "LQ05",
             "OR01", "OR02", "OR03", "OR05", "ST01", "ST02", "ST03", "RP01",
             "RR01", "RR02", "RR03", "IV02", "IV03"]
UNCHANGED = ["CR04", "CR05", "MR03", "OR04", "ST04", "CP01", "CP02", "CP03", "CP04",
             "LG01", "LG02", "LG03", "LG04", "RP02", "RP03", "RP04", "RR04", "IV01", "IV04"]


def test_all_transmission_rules_present(stress_cfg):
    assert sorted(stress_cfg["transmission"]) == sorted(SENSITIVE)
    assert sorted(stress_cfg["unchanged"]) == sorted(UNCHANGED)


def test_transmission_split_matches_stress_sensitive_flag(ra):
    flags = ra[ra.risk_type != "Capital Overlay"].set_index("kri_id").stress_sensitive
    assert sorted(flags[flags == "Y"].index) == sorted(SENSITIVE)
    assert sorted(flags[flags == "N"].index) == sorted(UNCHANGED)


def test_transmission_coefficients_match_spec(stress_cfg):
    t = stress_cfg["transmission"]
    assert stress_cfg["conventions"]["gdp_reference"] == 5.0
    assert (t["CR01"]["gdp_coef"], t["CR01"]["bps_coef"]) == (0.20, 0.10)
    assert (t["CR02"]["ref_kri"], t["CR02"]["multiplier"]) == ("CR01", 1.5)
    assert t["CR03"]["gdp_coef"] == 0.40
    assert t["MR01"]["variable"] == "idr_depreciation"
    assert t["MR02"]["rule"] == "scale_bps"
    lq1 = t["LQ01"]
    assert (lq1["excess_reserve"], lq1["placements"], lq1["sukuk_unencumbered"]) == (1500, 2000, 7000)
    assert (lq1["base_haircut"], lq1["net_outflow_30d_base"], lq1["dpk_base"]) == (0.05, 8750, 48000)
    assert (t["LQ02"]["financing"], t["LQ02"]["dpk_base"]) == (41000, 48000)
    assert t["LQ04"]["coef"] == 0.25
    assert t["OR02"]["rule"] == "scale_by_variable_ceil"
    assert (t["ST01"]["growth_target"], t["ST01"]["gdp_coef"]) == (15, 2.0)
    assert t["ST02"]["gdp_coef"] == -5.0
    assert t["ST03"]["gdp_coef"] == 2.0
    assert t["RP01"]["variable"] == "complaint_volume_uplift"
    assert (t["RR01"]["bps_coef"], t["RR02"]["bps_coef"], t["RR03"]["bps_coef"]) == (0.30, 0.20, -0.25)
    assert t["IV02"]["gdp_coef"] == 0.8
    assert t["IV03"]["variable"] == "sukuk_mv_shock_fvoci"


def test_capital_overlay_parameters_match_spec(stress_cfg):
    c = stress_cfg["capital_overlay"]
    assert (c["credit_loss"]["financing"], c["credit_loss"]["loss_rate"]) == (41000, 0.45)
    assert c["investment_loss"]["fvoci_portfolio"] == 6000
    assert c["operational_loss"]["annual_loss_base"] == 90
    assert (c["dcr_cost"]["deposito_mudharabah"], c["dcr_cost"]["pass_through"]) == (24000, 0.50)
    assert (c["capital"]["capital_base"], c["atmr"]["atmr_base"]) == (7000, 40000)
    assert c["capital"]["include_current_profit"] is False


def test_yaml_variables_exist_in_macro_scenarios(stress_cfg):
    variables = set(pd.read_csv(REF / "macro_scenarios.csv").variable)
    found = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.endswith("variable"):
                    found.append(v)
                walk(v)
    walk(stress_cfg)
    assert found and set(found) <= variables


def test_capital_overlay_arithmetic_reproduces_spec_table(stress_cfg):
    """Cross-check YAML → angka §5.5 (bukan engine; hanya memastikan parameter tidak salah ketik)."""
    c = stress_cfg["capital_overlay"]; t = stress_cfg["transmission"]["CR01"]
    mac = pd.read_csv(REF / "macro_scenarios.csv").set_index("variable")
    expected = {"adverse": (567, 15.8), "severe": (1513, 13.1)}
    for s, (loss, kpmm) in expected.items():
        m = mac[s]; dg = 5.0 - m.gdp_growth; bps = m.policy_rate_shift
        dnpf = t["gdp_coef"] * dg + t["bps_coef"] * bps / 100
        total = (dnpf / 100 * c["credit_loss"]["financing"] * c["credit_loss"]["loss_rate"]
                 + c["investment_loss"]["fvoci_portfolio"] * abs(m.sukuk_mv_shock_fvoci) / 100
                 + c["operational_loss"]["annual_loss_base"] * m.operational_event_uplift / 100
                 + c["dcr_cost"]["deposito_mudharabah"] * bps / 10000 * c["dcr_cost"]["pass_through"])
        atmr = c["atmr"]["atmr_base"] * (1 + m.rwa_uplift / 100)
        assert round(total) == loss
        assert round((c["capital"]["capital_base"] - total) / atmr * 100, 1) == kpmm


# ---------- bank_profile.yaml (spec §2) ----------
def test_bank_profile_matches_spec(profile):
    bs = profile["balance_sheet_2026_09"]; a = bs["assets"]; l = bs["liabilities_equity"]
    assert (a["cash_and_bi_current_account"], a["placements_with_other_banks"], a["sukuk_portfolio"],
            a["gross_financing"], a["allowance_for_losses"], a["other_assets"]) == (5000, 2000, 10000, 41000, -1000, 3000)
    assert a["cash_and_bi_detail"] == {"reserve_requirement_gwm": 3500, "excess_reserve": 1500}
    assert a["sukuk_detail"] == {"fvoci": 6000, "amortized_cost": 4000, "unencumbered": 7000}
    assert (l["giro_wadiah"], l["tabungan"], l["deposito_mudharabah"], l["other_funding"],
            l["other_liabilities"], l["equity"]) == (8000, 16000, 24000, 4000, 1000, 7000)
    assert profile["capital"] == {"capital_kpmm": 7000, "atmr": 40000, "kpmm_pct": 17.5}
    assert profile["income"]["gross_income_annual"] == 5600
    f = profile["financing"]
    assert (f["umkm_share_pct"], f["umkm_outstanding"], f["growth_target_yoy_pct"]) == (30, 12300, 15)
    r = profile["reporting"]
    assert (r["random_seed"], r["period_start"], r["period_end"]) == (42, "2025-10", "2026-09")


def test_bank_profile_internally_consistent(profile):
    bs = profile["balance_sheet_2026_09"]; a = bs["assets"]; l = bs["liabilities_equity"]
    assets = sum(a[k] for k in ["cash_and_bi_current_account", "placements_with_other_banks",
                                "sukuk_portfolio", "gross_financing", "allowance_for_losses", "other_assets"])
    dpk = l["giro_wadiah"] + l["tabungan"] + l["deposito_mudharabah"]
    assert assets == a["total_assets"] == 60000
    assert dpk == l["total_dpk"] == 48000
    assert dpk + l["other_funding"] + l["other_liabilities"] + l["equity"] == l["total_liabilities_equity"] == 60000
    assert sum(a["cash_and_bi_detail"].values()) == a["cash_and_bi_current_account"]
    assert a["sukuk_detail"]["fvoci"] + a["sukuk_detail"]["amortized_cost"] == a["sukuk_portfolio"]
    cap = profile["capital"]
    assert cap["capital_kpmm"] / cap["atmr"] * 100 == pytest.approx(cap["kpmm_pct"])
    fin = profile["financing"]
    assert a["gross_financing"] * fin["umkm_share_pct"] / 100 == fin["umkm_outstanding"]


# ---------- reference tambahan (§6, §7, action library) ----------
def test_interdependency_edges_match_spec():
    e = pd.read_csv(REF / "interdependency_edges.csv")
    assert list(e.columns) == ["source", "target", "channel", "strength", "evidence"]
    assert len(e) == 11 and e.strength.between(1, 3).all()
    assert e.strength.sum() == 26


def test_emerging_risks_match_spec():
    e = pd.read_csv(REF / "emerging_risks.csv").set_index("er_id")
    assert list(e.reset_index().columns) == ["er_id", "risk_name", "driver", "description", "likelihood",
        "impact", "velocity", "priority_score", "linked_risk_types", "early_signal", "status", "owner", "next_review"]
    expected = {"ER01": (4, 5, 5, 20.0, "Watch"), "ER02": (3, 4, 4, 9.6, "Watch"), "ER03": (3, 4, 2, 4.8, "Monitor")}
    for er, (l, i, v, p, st) in expected.items():
        row = e.loc[er]
        assert (row.likelihood, row.impact, row.velocity, row.status) == (l, i, v, st)
        assert row.priority_score == pytest.approx(p) == pytest.approx(l * i * v / 5)
        assert set(row.linked_risk_types.split(";")) <= set(RISK_TYPES)


def test_action_library_one_per_kri_max_20_words(ra):
    a = pd.read_csv(REF / "action_library.csv")
    kris = ra[ra.risk_type != "Capital Overlay"]
    assert a.kri_id.is_unique and set(a.kri_id) == set(kris.kri_id)
    merged = a.merge(kris[["kri_id", "risk_type"]], on="kri_id", suffixes=("", "_ra"))
    assert (merged.risk_type == merged.risk_type_ra).all()
    assert (a.recommended_action.str.split().str.len() <= 20).all()
    assert a.recommended_action.str.strip().ne("").all()


def test_repository_structure():
    for p in ["README.md", "Makefile", "config", "data/reference", "data/raw", "data/output",
              "src/erm/generator", "src/erm/validation.py", "src/erm/kri.py", "src/erm/scoring.py",
              "src/erm/stress.py", "src/erm/capital.py", "src/erm/actions.py", "src/erm/export_powerbi.py",
              "tests", "notebooks", "excel", "dashboard", "regulatory", "report"]:
        assert (ROOT / p).exists(), p
    assert "fully synthetic data" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_bank_profile_slsi_matches_spec_and_decision(profile):
    s = profile["slsi"]
    assert s["haircut_sukuk_unencumbered"] == 0.05
    assert s["runoff_30d"] == {"giro_wadiah": 0.30, "tabungan": 0.12, "deposito_mudharabah": 0.12, "other_funding": 0.25}
    assert s["liquid_assets_2026_09"] == 10150
    assert (s["net_outflow_30d_anchor"], s["anchor_period"]) == (8750, "2026-09")   # keputusan user Fase 2
    assert round(s["liquid_assets_2026_09"] / s["net_outflow_30d_anchor"] * 100) == 116
