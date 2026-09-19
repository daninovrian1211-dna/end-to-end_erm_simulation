"""Fase 2 — generator data sintetis: rekonsiliasi (§12 no. 1, 2), reproducibility (§12 no. 7),
kalibrasi KRI terhadap risk_appetite.csv, dan storyline wajib."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from erm import kri, validation
from erm.generator import OUTPUT_FILES, calibrate, generate_all

ROOT = Path(__file__).resolve().parents[1]
PROFILE = yaml.safe_load((ROOT / "config" / "bank_profile.yaml").read_text(encoding="utf-8"))
REPORT_END = "2026-09"

SPEC_COLUMNS = {  # spec §8.2
    "balance_sheet_monthly": ["period", "line_item", "category", "sub_category", "amount"],
    "capital_monthly": ["period", "capital_kpmm", "atmr", "gross_income_ttm", "profit_ytd", "profit_budget_ytd"],
    "financing_portfolio": ["period", "obligor_id", "segment", "sector", "akad", "outstanding", "collectibility", "dpd",
                            "margin_type", "remaining_tenor_months", "origination_period"],
    "deposits_monthly": ["period", "product", "balance", "equivalent_rate", "market_benchmark_rate", "runoff_assumption"],
    "top_depositors": ["period", "depositor_id", "product", "balance", "rank"],
    "maturity_profile": ["period", "bucket", "assets_maturing", "liabilities_maturing", "rsa", "rsl"],
    "market_positions": ["period", "currency", "fx_assets", "fx_liabilities", "off_balance", "net_position"],
    "investment_portfolio": ["period", "holding_id", "issuer", "issuer_type", "instrument", "classification", "rating",
                             "face_value", "market_value", "modified_duration", "maturity_date", "encumbered_flag"],
    "rate_of_return_monthly": ["period", "financing_yield", "expected_depositor_return", "actual_depositor_return",
                               "profit_distribution_ratio", "nim"],
    "operational_events": ["event_id", "period", "event_date", "event_type", "business_unit", "channel", "severity",
                           "gross_loss", "recovery", "net_loss", "root_cause", "repeat_flag", "sla_days",
                           "resolution_days", "status"],
    "compliance_events": ["breach_id", "period", "source", "regulation_ref", "severity", "business_unit",
                          "target_remediation_date", "closed_date", "repeat_flag", "status"],
    "legal_cases": ["case_id", "open_period", "case_type", "counterparty_type", "severity", "potential_loss",
                    "provisioned_flag", "status", "closed_period"],
    "complaints": ["complaint_id", "period", "channel", "category", "severity", "sla_days", "resolution_days", "status"],
    "sentiment_monthly": ["period", "source", "mentions", "negative_mentions"],
    "strategic_monthly": ["period", "financing_growth_yoy", "financing_growth_target", "cost_to_income",
                          "initiatives_total", "initiatives_delayed"],
}


@pytest.fixture(scope="session")
def run_dirs(tmp_path_factory):
    a, b = tmp_path_factory.mktemp("run_a"), tmp_path_factory.mktemp("run_b")
    generate_all(a)
    generate_all(b)
    return a, b


@pytest.fixture(scope="session")
def raw(run_dirs):
    return kri.load_raw(run_dirs[0])


@pytest.fixture(scope="session")
def kri_values(raw):
    return kri.compute_kri_values(raw).pivot(index="period", columns="kri_id", values="value")


# ---------- struktur ----------
def test_all_spec_files_with_spec_columns(raw):
    assert set(OUTPUT_FILES) == set(SPEC_COLUMNS)
    for name, cols in SPEC_COLUMNS.items():
        assert list(raw[name].columns) == cols, name


def test_period_coverage(raw):
    assert sorted(raw["balance_sheet_monthly"].period.unique()) == calibrate.MONTHLY_PERIODS
    assert set(calibrate.REPORT_PERIODS) <= set(raw["financing_portfolio"].period)
    assert raw["operational_events"].period.min() == "2024-10"
    assert raw["operational_events"].period.max() == REPORT_END


# ---------- §12 no. 1: rekonsiliasi neraca ----------
def test_balance_sheet_balances_every_month(raw):
    chk = validation.balance_check(raw["balance_sheet_monthly"])
    assert len(chk) == len(calibrate.MONTHLY_PERIODS)
    assert chk.difference.abs().max() <= validation.ABS_TOL


def test_reporting_date_matches_anchor_balance_sheet(raw):
    chk = validation.anchor_check(raw["balance_sheet_monthly"], raw["capital_monthly"], PROFILE)
    assert chk.within_tolerance.all(), chk[~chk.within_tolerance]


# ---------- §12 no. 2: rekonsiliasi granular ----------
def test_granular_reconciliation_every_month(raw):
    rec = validation.granular_reconciliation(raw)
    assert set(rec.item) >= {"Pembiayaan bruto", "Portofolio sukuk", "Total DPK"}
    assert rec.reconciled.all(), rec[~rec.reconciled]


def test_top_depositors_within_product_balance(raw):
    assert validation.top_depositor_check(raw).ok.all()


# ---------- §12 no. 7: reproducible ----------
def test_two_runs_seed_42_identical_hashes(run_dirs):
    ha, hb = (validation.file_hashes(d) for d in run_dirs)
    assert len(ha) == len(OUTPUT_FILES) and ha == hb


def test_different_seed_changes_output(tmp_path, run_dirs):
    generate_all(tmp_path, seed=43)
    assert validation.file_hashes(tmp_path) != validation.file_hashes(run_dirs[0])


# ---------- kalibrasi KRI ----------
def _score(x, direction, cuts):
    for i, c in enumerate(cuts, 1):
        if (x <= c if direction == "lower" else x >= c):
            return i
    return 5


def test_sep_2026_values_produce_target_score(kri_values):
    ra = calibrate.load_risk_appetite()
    bad = []
    for r in ra.itertuples():
        val = kri_values.at[REPORT_END, r.kri_id]
        if _score(val, r.direction, [r.c1, r.c2, r.c3, r.c4]) != r.target_score:
            bad.append((r.kri_id, val, r.target_score))
    assert not bad
    assert len(ra[ra.risk_type != "Capital Overlay"]) == 42


def test_kri_paths_start_and_end_near_reference(kri_values):
    """Okt-2025 ≈ value_start dan Sep-2026 ≈ value_target (≤ 20% rentang cut-point; granularitas integer/rasio)."""
    ra = calibrate.load_risk_appetite().set_index("kri_id")
    rng = (ra.c4 - ra.c1).abs()
    d_start = ((kri_values.loc["2025-10"] - ra.value_start_2025_10) / rng).abs()
    d_end = ((kri_values.loc[REPORT_END] - ra.value_target_2026_09) / rng).abs()
    assert d_start.max() <= 0.20, d_start.sort_values().tail(3)
    assert d_end.max() <= 0.20, d_end.sort_values().tail(3)


# ---------- storyline wajib ----------
def test_story_npf_rises_gradually(kri_values):
    npf = kri_values["CR01"]
    assert npf.iloc[-1] > npf.iloc[6] > npf.iloc[0]
    assert (npf.diff().dropna() > -0.05).all()


def test_story_digital_incident_surge_since_june_process_failure(raw):
    ops = raw["operational_events"]
    rep = ops[ops.period.isin(calibrate.REPORT_PERIODS)]
    monthly = rep.groupby("period").size()
    assert monthly.loc["2026-06":].min() > monthly.loc[:"2026-05"].max()
    surge = rep[rep.period >= "2026-06"]
    digital = surge[(surge.channel == "Mobile banking") & (surge.root_cause == "Process failure")]
    before = rep[rep.period < "2026-06"]
    assert len(digital) / len(surge) > 2 * ((before.channel == "Mobile banking") & (before.root_cause == "Process failure")).mean()
    assert rep.root_cause.value_counts().idxmax() == "Process failure"


def test_story_dpk_falls_and_gap_widens_last_4_months(raw, kri_values):
    b = raw["balance_sheet_monthly"]
    dpk = b[b.sub_category == "dpk"].groupby("period").amount.sum()
    last5 = dpk.loc["2026-05":"2026-09"]
    assert (last5.diff().dropna() < 0).all()
    lq04 = kri_values["LQ04"]
    assert (lq04.loc["2026-06":].diff().dropna() > 0).all()
    assert lq04.loc["2026-09"] - lq04.loc["2026-05"] > 3.0


def test_story_financing_growth_22pct(raw):
    b = raw["balance_sheet_monthly"]
    fin = b[b.line_item == "pembiayaan_bruto"].set_index("period").amount
    assert fin["2026-09"] / fin["2025-09"] - 1 == pytest.approx(0.22, abs=1e-6)
    s = raw["strategic_monthly"].set_index("period")
    assert s.at["2026-09", "financing_growth_yoy"] == pytest.approx(22.0)


def test_story_two_of_three_overdue_high_breaches_are_akad_dps(raw):
    c = raw["compliance_events"].copy()
    end = pd.Timestamp("2026-09-30")
    c["closed_date"] = pd.to_datetime(c.closed_date)
    overdue = c[(c.severity == "High") & (pd.to_datetime(c.target_remediation_date) < end)
                & (c.closed_date.isna() | (c.closed_date > end))]
    assert len(overdue) == 3
    akad = overdue.regulation_ref.str.contains("akad") & overdue.regulation_ref.str.contains("opini DPS")
    assert akad.sum() == 2


def test_story_complaint_spike_aug_sep_mobile_banking(raw, kri_values):
    rp01 = kri_values["RP01"]
    assert rp01.loc["2026-08"] > 15 and rp01.loc["2026-09"] > 20
    assert rp01.loc[:"2026-07"].max() < 10
    c = raw["complaints"]
    share = lambda ps: (c[c.period.isin(ps)].category == "Gangguan transaksi mobile banking").mean()
    assert share(["2026-08", "2026-09"]) > 2 * share(calibrate.REPORT_PERIODS[:10])


def test_scope_guard_generator_names():
    banned = ["ecl", "ckpn", "pd_model", "lgd", "var_", "monte_carlo", "sklearn"]
    src = ROOT / "src"
    for path in src.rglob("*.py"):
        assert not any(b in path.name.lower() for b in banned), path
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("def ") or s.startswith("class "):
                name = s.split()[1].split("(")[0].lower()
                assert not any(b in name for b in banned), (path, name)
