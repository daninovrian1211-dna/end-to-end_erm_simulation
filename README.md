# Enterprise Risk Management Framework for an Islamic Bank

**Risk Appetite, Monitoring & Stress Testing — PT Amanah Syariah Bank (ASB, fictional)**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Complete-brightgreen)]()

> **Disclaimer.** This project uses a fictional Islamic bank and fully synthetic data. All risk appetite thresholds, scenarios, sensitivities, and scoring rules are project-specific analytical assumptions created for educational and portfolio purposes. They do not represent any actual bank's internal limits, regulatory thresholds, or an official OJK risk profile rating.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Project Structure](#project-structure)
- [Architecture & Data Flow](#architecture--data-flow)
- [Getting Started](#getting-started)
- [File Descriptions](#file-descriptions)
- [Key Results (Sep-2026)](#key-results-sep-2026)
- [Methodology](#methodology)
- [Design Decisions](#design-decisions)
- [Limitations](#limitations)
- [Development Status](#development-status)
- [License](#license)

---

## Overview

This project is a full **Enterprise Risk Management (ERM) Framework** for an Islamic commercial bank (*Bank Umum Syariah*) — not just a dashboard. The framework answers five core governance questions:

| # | Question | Framework Answer |
|---|---|---|
| 1 | **How much risk is the bank allowed to take?** | Risk appetite, early warning triggers, and risk limits for 42 KRIs |
| 2 | **Where does the bank stand right now?** | Scores for 10 risk types and an enterprise score, with model score vs. judgment override shown side by side |
| 3 | **Which direction is it heading?** | Trend analysis and early warning signals (emerging breach) |
| 4 | **What happens if conditions deteriorate?** | 3-scenario stress testing and a Capital Adequacy Overlay (CAR/KPMM) |
| 5 | **Who does what?** | Rule-based management actions, an interdependency map, and an emerging risk register |

Islamic banking characteristics are made explicit throughout: profit-sharing (*bagi hasil*), *displaced commercial risk*, Sharia Supervisory Board (DPS) findings, and contract compliance (murabahah, musyarakah, ijarah, mudharabah).

---

## Key Features

- **42 KRIs + 1 Capital Overlay** covering 10 risk types: Credit, Market, Liquidity, Operational, Strategic, Compliance, Legal, Reputation, Rate of Return, Investment
- **Deterministic synthetic data generator** (seed 42) calibrated against a Sep-2026 anchor balance sheet (IDR 60,000 billion)
- **Scoring engine** with a 5-zone scale, floor rule, judgment override, trend analysis, and early warning
- **Enterprise stress testing** across 3 scenarios (Baseline, Adverse, Severe) with 23 YAML-driven macro transmission rules
- **Capital Adequacy Overlay (KPMM/CAR)**: stress impact on bank capital adequacy
- **Automated management action tracker**: triggered by breach episodes (score ≥ 4), with an action library and Board/RMC escalation for score 5
- **Excel framework** (10 sheets with live formulas, reconciled against the engine)
- **Power BI star schema** (5 dimension tables + 8 fact tables, 13 DAX measures)
- **Audited executive report PDF** (every figure's source is logged in `*_facts.json`)
- **5-phase test suite** (pytest) verifying end-to-end pipeline integrity from spec to deliverables

---

## Project Structure

```
enterprise-risk-management/
│
├── config/
│   ├── bank_profile.yaml           # Bank profile & anchor balance sheet (§2)
│   └── stress_parameters.yaml      # Stress transmission coefficients & capital overlay (§5.2, §5.5)
│
├── data/
│   ├── raw/                        # Generator output (15 CSV files)
│   ├── output/                     # Engine output (9 CSV files)
│   └── reference/                  # Read-only reference data (spec, thresholds, weights, scenarios)
│       ├── ERM_Blueprint_v3_Spec.md
│       ├── risk_appetite.csv
│       ├── risk_weights.csv
│       ├── macro_scenarios.csv
│       ├── judgment_overrides.csv
│       ├── interdependency_edges.csv
│       ├── emerging_risks.csv
│       ├── action_library.csv
│       ├── reference_calc.py
│       └── reference_output.txt
│
├── src/erm/
│   ├── generator/                  # Synthetic data generators per risk domain
│   │   ├── calibrate.py
│   │   ├── balance_sheet.py
│   │   ├── credit.py
│   │   ├── liquidity.py
│   │   ├── market.py
│   │   ├── investment.py
│   │   ├── operational.py
│   │   ├── compliance.py
│   │   ├── legal.py
│   │   ├── reputation.py
│   │   ├── rate_of_return.py
│   │   └── strategic.py
│   ├── kri.py                      # Computation of 42 KRI values + CAP01
│   ├── scoring.py                  # Scoring methodology (§3)
│   ├── stress.py                   # Enterprise stress testing (§5.1–5.4)
│   ├── capital.py                  # Capital Adequacy Overlay (§5.5)
│   ├── actions.py                  # Management action tracker (§8.4)
│   ├── validation.py               # Data reconciliation & validation (§12)
│   ├── datastore.py                # Centralized access to outputs & reference data
│   ├── excel_framework.py          # Excel framework builder (§10)
│   ├── export_powerbi.py           # Power BI star schema exporter (§9)
│   ├── report.py                   # Executive report PDF generator
│   ├── __main__.py                 # CLI: engine | excel | powerbi | report
│   └── __init__.py
│
├── tests/
│   ├── test_phase1_reference.py    # Reference data & configuration integrity
│   ├── test_phase2_generator.py    # Synthetic data validation & balance sheet reconciliation
│   ├── test_phase3_scoring.py      # KRI engine, scoring & enterprise profile
│   ├── test_phase4_stress.py       # Stress testing & capital overlay
│   └── test_phase5_deliverables.py # Excel, Power BI, report PDF, README
│
├── excel/
│   └── ERM_Framework.xlsx          # Excel framework (10 sheets, live formulas)
│
├── dashboard/
│   ├── model/                      # Star schema CSVs (13 files) for Power BI
│   ├── powerbi_spec.md             # Guide for assembling the dashboard in Power BI Desktop
│   └── DAX_measures.md             # All DAX measures
│
├── report/
│   ├── ERM_Executive_Report.pdf    # Executive report PDF
│   └── ERM_Executive_Report_facts.json  # Audit trail for every figure in the report
│
├── regulatory/
│   └── Regulatory_Mapping.xlsx     # KRI-to-OJK-regulation mapping (§11)
│
├── notebooks/
│   ├── 01_data_generation.ipynb
│   ├── 02_kri_risk_appetite.ipynb
│   ├── 03_trend_early_warning.ipynb
│   ├── 04_stress_capital.ipynb
│   └── 05_reporting.ipynb
│
├── docs/
│   ├── Panduan_Penggunaan_ERM.pdf  # Non-technical user guide
│   └── Panduan_Penggunaan_ERM.tex
│
├── run_all.py                      # Cross-platform alternative to `make all`
├── Makefile
└── pyproject.toml
```

---

## Architecture & Data Flow

```
bank_profile.yaml
risk_appetite.csv       ──►  generator/ (seed 42)  ──►  data/raw/   (15 CSV files)
                                                               │
                                                               ▼
                                                          kri.py
                                                               │
                                                               ▼
                                                         scoring.py
                                                               │
                              ┌────────────────────────────────┤
                              │                                ▼
                              │              kri_monthly / risk_scores_monthly
                              │              enterprise_profile_monthly
                              │                                │
                  stress_parameters.yaml                       │
                  macro_scenarios.csv     ──►  stress.py  ◄────┘
                                                    │
                                                    ▼
                                              capital.py
                                                    │
                                                    ▼
                                              actions.py
                                                    │
                                              data/output/
                                                    │
                         ┌──────────────────────────┤───────────────────┐
                         ▼                          ▼                   ▼
                  excel_framework.py        export_powerbi.py        report.py
                         │                          │                   │
                         ▼                          ▼                   ▼
               excel/ERM_Framework.xlsx   dashboard/model/*.csv   report/*.pdf
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- LibreOffice *(optional: recalculates Excel formulas at build time; without it, Excel recalculates when the file is opened)*

### Installation

```bash
git clone https://github.com/<username>/enterprise-risk-management.git
cd enterprise-risk-management
pip install -e ".[dev]"
```

### Running the Pipeline

**Using `make` (Linux/macOS):**

```bash
make all         # full pipeline: data → engine → report → test
```

**Using `run_all.py` (Windows/cross-platform):**

```bash
python run_all.py            # full pipeline
python run_all.py --no-test  # skip pytest
```

### Individual `make` Targets

| Target | Command | Output |
|---|---|---|
| Synthetic data | `make data` | `data/raw/` (15 CSV files, seed 42) |
| KRI & scoring engine | `make engine` | `data/output/` (9 CSV files) |
| Excel framework | `make excel` | `excel/ERM_Framework.xlsx` |
| Power BI package | `make powerbi` | `dashboard/model/*.csv` (13 files) |
| Full report | `make report` | `excel/` + `dashboard/model/` + `report/ERM_Executive_Report.pdf` |
| Test suite | `make test` | Acceptance tests (pytest) |
| Reference check | `make reference` | Regression baseline verification |

> **Required order:** `make data` → `make engine` → `make report` → `make test`

### Direct CLI

```bash
# Run the engine only (KRI, scoring, stress, capital, actions)
python -m erm engine [--raw data/raw] [--out data/output]

# Build the Excel framework
python -m erm excel

# Build the Power BI star schema
python -m erm powerbi

# Build the executive report PDF
python -m erm report

# Generate synthetic data only
python -m erm.generator [--out data/raw] [--seed 42]
```

---

## File Descriptions

### `config/`

| File | Description |
|---|---|
| `bank_profile.yaml` | Complete profile of the fictional PT Amanah Syariah Bank: the Sep-2026 anchor balance sheet (IDR 60,000 billion), capital parameters (CAR 17.5%), SLSI parameters, the deterministic seed (42), and the reporting period (Oct-2025 to Sep-2026). Acts as the single source of truth for all modules. |
| `stress_parameters.yaml` | Macro transmission coefficients for 23 macro-sensitive KRIs (additive, multiple_of_delta, scale_by_variable, etc.) and capital adequacy overlay parameters (credit loss rate, investment loss, operational loss, DCR cost). All values are read at runtime — nothing is hard-coded in Python. |

### `data/reference/`

| File | Description |
|---|---|
| `ERM_Blueprint_v3_Spec.md` | The single source of truth for the entire project: definitions of 42 KRIs + CAP01, scoring methodology (§3), stress testing (§5), data generation (§8.2), deliverables (§9–§11), and acceptance criteria (§12). |
| `risk_appetite.csv` | Four cut-point thresholds per KRI (c1–c4), direction, within-risk-type weight, Oct-2025 starting value, Sep-2026 target value, target score, and stress-sensitive flag. |
| `risk_weights.csv` | Materiality weights for the 10 risk types used in enterprise score aggregation, measurement approach, and depth of analysis. |
| `macro_scenarios.csv` | Three macro scenarios (Baseline, Adverse, Severe): GDP growth, policy rate shift (bps), IDR depreciation, and other shock variables. |
| `judgment_overrides.csv` | Score overrides based on expert judgment: delta, rationale, approver, and validity period. Applies per period; the delta is carried through to all stress scenarios. |
| `interdependency_edges.csv` | Risk type dependency graph (source → target, strength, mechanism) for the interdependency map. |
| `emerging_risks.csv` | Register of developing risks: risk type, severity, likelihood, description, and time horizon. |
| `action_library.csv` | Standardized remediation actions per KRI: recommended action text and action owner. Used by `actions.py` to ensure consistent, auditable action wording. |
| `reference_calc.py` | Standalone reference calculation (pure Python, no imports from `src/erm`) used for regression testing; produces `reference_output.txt`. |
| `reference_output.txt` | Expected output of `reference_calc.py`, used by `test_phase1_reference.py` as the regression baseline. |
| `CHECKSUMS.sha256` | SHA-256 hashes of reference files for integrity verification. |

### `data/raw/` (generator output)

| File | KRIs Derived | Description |
|---|---|---|
| `balance_sheet_monthly.csv` | CR01–05, MR01–03, LQ01–05, RR01–04 | Monthly balance sheet (assets, liabilities, equity) derived backwards from the Sep-2026 anchor |
| `capital_monthly.csv` | CAP01 | Monthly capital adequacy ratio (CAR/KPMM) and risk-weighted assets (ATMR) |
| `financing_portfolio.csv` | CR01–05 | Financing portfolio per obligor: segment, sector, contract type, collectibility (6,000 obligors) |
| `deposits_monthly.csv` | LQ01–05 | Monthly DPK composition (giro wadiah, tabungan, deposito mudharabah) |
| `top_depositors.csv` | LQ03 | Top-20 depositor data for depositor concentration measurement |
| `maturity_profile.csv` | LQ04–05 | Asset and liability maturity buckets |
| `market_positions.csv` | MR01 | Net Open Position (PDN) per currency |
| `investment_portfolio.csv` | MR02, IV01–IV04 | Sukuk portfolio: issuer, rating, market value, duration, FVOCI/amortized cost classification |
| `rate_of_return_monthly.csv` | RR01–04 | Profit-sharing rates (DPK vs. market benchmark, financing margin) |
| `operational_events.csv` | OR01–05 | Operational event log: category, severity, root cause, financial loss |
| `compliance_events.csv` | CP01–04 | Compliance finding log: remediation status, finding type, target date |
| `legal_cases.csv` | LG01–04 | Legal case list: claim value, status, aging |
| `complaints.csv` | RP01–04 | Customer complaint log: category, severity, resolution status |
| `sentiment_monthly.csv` | RP02 | Monthly media/social sentiment score |
| `strategic_monthly.csv` | ST01–04 | Actual vs. target: financing growth, profit, and efficiency metrics |

### `data/output/` (engine output)

| File | Description |
|---|---|
| `kri_monthly.csv` | Values and scores for all 42 KRIs + CAP01 per month, including zone, utilization, trend, early warning flag, and label |
| `risk_scores_monthly.csv` | Risk score per risk type per month: weighted score, floor adjustment, model score, override delta, final score, rating, and color |
| `enterprise_profile_monthly.csv` | Monthly enterprise score: score, rating, limit utilization, tolerance/limit breach counts, and emerging risk count |
| `stress_results.csv` | KRI values under 3 stress scenarios (baseline/adverse/severe): base value, stressed value, delta, and stressed score |
| `stress_risk_scores.csv` | Risk score per type per stress scenario |
| `stress_enterprise_summary.csv` | Enterprise score, rating, and utilization per stress scenario |
| `stress_waterfall.csv` | Decomposition of stress impact per KRI (waterfall chart data) |
| `capital_overlay.csv` | CAR/KPMM before and after stress per scenario: loss breakdown (credit, investment, operational, DCR) |
| `management_actions.csv` | Rule-triggered actions: action_id, KRI, severity, recommended action, owner, due date, status |

### `src/erm/` (source code)

| File | Description |
|---|---|
| `generator/calibrate.py` | Calibration infrastructure: period definitions (3-month lookback + 12 reporting months), KRI target paths (value_start → value_target with 1.5% noise), and the `rake()` function that adjusts granular data so aggregates follow target paths. |
| `generator/balance_sheet.py` | Builds the core monthly aggregates (financing, deposits, equity, liquidity) derived backwards from the anchor balance sheet. Acts as the control total for all other domain data. |
| `generator/credit.py` | Financing portfolio per obligor: sector distribution, contract types, lognormal sizing, and calibrated collectibility migration (Kol-2 → NPF). |
| `generator/liquidity.py` | DPK data (giro wadiah, tabungan, deposito mudharabah), top depositors, and maturity profile. |
| `generator/market.py` | Monthly Net Open Position (PDN) across multiple currencies. |
| `generator/investment.py` | Sukuk portfolio: per-instrument holdings, monthly market values, modified duration, ratings, FVOCI/AC classification. |
| `generator/operational.py` | Operational event log based on distributions of category, severity, root cause, and loss values. |
| `generator/compliance.py` | Compliance findings (regulatory and Sharia) with remediation status. |
| `generator/legal.py` | Legal cases: claim values, aging, status. |
| `generator/reputation.py` | Monthly complaint volume and severity, media/social sentiment scores. |
| `generator/rate_of_return.py` | DPK profit-sharing rates vs. benchmark and repricing gap. |
| `generator/strategic.py` | Actual vs. target: financing growth, net income, BOPO, and strategic initiative achievement. |
| `kri.py` | Computes the numerical value of all 42 KRIs + CAP01 from raw data using the operational definitions in spec §8.2. This module only computes values — scoring lives in `scoring.py`. |
| `scoring.py` | The core scoring engine (§3): converts KRI values to 1–5 scores, applies the floor rule, judgment overrides, OLS-based trend analysis (3-month window), early warning projections (6-month OLS, 3-month horizon), risk type scores, enterprise score with escalation rule, and risk ratings. |
| `stress.py` | Interprets the YAML transmission rules in `stress_parameters.yaml` and applies them to Sep-2026 KRI values to produce stressed values under 3 scenarios. Re-scoring is delegated entirely to `scoring.py` — no duplicated logic. |
| `capital.py` | Computes CAR/KPMM before and after stress: decomposes total loss into credit loss (from ΔNPF), investment loss (sukuk FVOCI shock), operational loss uplift, and profit-sharing cost increase (DCR). |
| `actions.py` | Automatically creates management actions per breach episode (first time a KRI enters score 4, or escalates to score 5). Action text comes from `action_library.csv`; status (Open/Overdue/Closed/Superseded) is computed automatically. |
| `validation.py` | Verifies balance sheet reconciliation (total assets = total liabilities + equity), anchor checks (reporting date values vs. anchor balance sheet ±0.5%), and reproducibility hashes (seed 42). |
| `datastore.py` | Centralized read access to all engine outputs and reference data. Excel, Power BI, and report modules only read data through this module — a single gateway with no direct file reads in deliverable modules. |
| `excel_framework.py` | Builds `ERM_Framework.xlsx` (10 sheets) using openpyxl: risk taxonomy, risk appetite statement, KRI definitions, thresholds, scoring methodology, risk assessment, stress scenarios, management actions, regulatory mapping, and change log. Sheets 04–07 contain live Excel formulas. |
| `export_powerbi.py` | Builds the star schema (5 dimension + 8 fact tables) for Power BI: dim_date, dim_risk, dim_kri, dim_scenario, dim_business_unit, and fact tables for monthly monitoring and stress results. |
| `report.py` | Generates the executive report PDF (A4, 20+ pages) using ReportLab and matplotlib. Every figure printed in the narrative is logged with its data source in `ERM_Executive_Report_facts.json`. |
| `__main__.py` | CLI entry point: orchestrates the pipeline and parameterizes input/output paths. |

### `tests/`

| File | Description |
|---|---|
| `test_phase1_reference.py` | Verifies reference data integrity: 42 KRIs match spec §4, YAML config matches spec §2 & §5, reference file checksums, and `reference_calc.py` output matches the engine. |
| `test_phase2_generator.py` | Validates synthetic data: balance sheet reconciliation (balance check & anchor check ±0.5%), completeness of 15 raw files, data types and formats. |
| `test_phase3_scoring.py` | Verifies KRI engine calculations, per-KRI scores, per-risk-type scores (weighted, floor, override, final), and the Sep-2026 enterprise score against `reference_output.txt`. |
| `test_phase4_stress.py` | Verifies stress results (23 transmission rules) and capital overlay (CAR/KPMM for baseline/adverse/severe) against spec §5. |
| `test_phase5_deliverables.py` | End-to-end consistency verification: Excel figures match `data/output`; `facts.json` from the report matches the engine; Power BI star schema is complete and correct; pipeline is deterministic (re-running with seed 42 produces identical output). |

### `dashboard/`

| File | Description |
|---|---|
| `model/*.csv` | 13 star schema files ready to import into Power BI Desktop: 5 dimension tables (`dim_date`, `dim_risk`, `dim_kri`, `dim_scenario`, `dim_business_unit`) and 8 fact tables. |
| `powerbi_spec.md` | Complete guide for assembling the Power BI dashboard: data import steps, column types, table relationships, specifications for 5 report pages (Enterprise Overview, Risk Appetite, Trend & Early Warning, Stress Testing, Management Actions), and visual design (color theme, fonts). |
| `DAX_measures.md` | All required DAX measures: KRI Value, KRI Score, Risk Final Score, Enterprise Score, Deteriorating KRI Count, Limit Utilization, and supporting helper measures. |

### Other Files

| File | Description |
|---|---|
| `run_all.py` | Cross-platform alternative to `make all` (works on Windows). Runs all 5 pipeline steps sequentially with progress output. |
| `Makefile` | Make targets for each pipeline stage. |
| `pyproject.toml` | Python package configuration: dependencies (pandas, numpy, pyyaml, openpyxl, matplotlib, reportlab, pdfplumber, pillow), pytest setup, and package discovery. |
| `regulatory/Regulatory_Mapping.xlsx` | Mapping of the 42 KRIs to relevant OJK regulations, verified as of 17-Sep-2026 from JDIH BPK and the OJK website. |
| `docs/Panduan_Penggunaan_ERM.pdf` | Non-technical user guide (in Bahasa Indonesia): how to interpret scores, read the dashboard, and make decisions using the ERM framework. |
| `notebooks/01–05.ipynb` | Narrative Jupyter notebooks for each phase: data generation, KRI & risk appetite, trend & early warning, stress & capital, and reporting. Notebooks only call functions from `src/erm` — no business logic inside. |

---

## Key Results (Sep-2026)

The following figures are the engine's output at reporting date 30 September 2026 (all values verified by the test suite):

### Enterprise Score Trend

| Period | Enterprise Score | Rating |
|---|---|---|
| Oct-2025 | 1.9 | Low to Moderate |
| Jan-2026 | 2.1 | Low to Moderate |
| Apr-2026 | 2.2 | Low to Moderate |
| Jun-2026 | 2.5 | Moderate |
| Sep-2026 | **3.0** | **Moderate** |

### Risk Score by Type (Sep-2026)

| Risk Type | Weight | Model Score | Final Score | Rating |
|---|---:|---|---|---|
| Credit | 25% | Moderate | Moderate | 🟡 Amber |
| Market | 5% | Moderate | Moderate | 🟡 Amber |
| Liquidity | 15% | Moderate | Moderate | 🟡 Amber |
| Operational | 12% | Moderate | Moderate | 🟡 Amber |
| Strategic | 8% | Low to Moderate | Low to Moderate | 🟢 Green |
| Compliance | 8% | Moderate (+0.3 override) | Moderate to High | 🔴 Red |
| Legal | 4% | Low to Moderate | Low to Moderate | 🟢 Green |
| Reputation | 6% | Moderate | Moderate | 🟡 Amber |
| Rate of Return | 10% | Moderate | Moderate | 🟡 Amber |
| Investment | 7% | Low to Moderate | Low to Moderate | 🟢 Green |

### Stress Test Summary

| | Baseline | Adverse | Severe |
|---|---|---|---|
| Enterprise score | 3.0 — Moderate | 3.4 — Moderate | 4.0 — Moderate to High |
| Limit utilization | 68% | 78% | 93% |
| KRIs score ≥4 / score 5 | 9 / 0 | 14 / 6 | 21 / 14 |
| CAR (KPMM) | 17.5% | 15.8% | 13.1% |

---

## Methodology

### KRI Scoring (§3.1)

Each KRI has 4 cut-points (`c1`–`c4`) and a direction (`lower` or `higher` is better):

| Score | Zone | Color | Governance Meaning |
|---|---|---|---|
| 1 | Strong | 🟢 Green | Well within appetite |
| 2 | Within appetite | 🟢 Green | Below risk appetite (`c2`) |
| 3 | Watch | 🟡 Amber | Above appetite, below early warning trigger (`c3`) |
| 4 | Tolerance breach | 🔴 Red | Above trigger, below risk limit (`c4`) |
| 5 | Limit breach | 🔴 Red | Above limit → escalation to Board/RMC |

### Risk Score per Type (§3.2)

```
weighted = Σ (kri_score × kri_weight)   # weights within each risk type sum to 1.00
floor    = max(kri_score) − 1.5
model    = max(weighted, floor)
final    = model + override_delta        # capped at 1.0–5.0
```

The floor rule prevents a single critical KRI from being masked by the weighted average.

### Stress Testing (§5.1–5.4)

Three macro scenarios (Baseline, Adverse, Severe) are applied to the Sep-2026 KRI values using 23 transmission rules defined in `stress_parameters.yaml`. The horizon is 12 months, with a static balance sheet and no management actions (gross stress impact).

### Capital Adequacy Overlay (§5.5)

```
total_loss = credit_loss + investment_loss + operational_loss + dcr_cost
capital    = capital_base − total_loss
kpmm       = capital / (atmr × atmr_uplift) × 100
```

---

## Design Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **42 KRIs + 1 capital overlay (CAP01)** | The §4 table and `risk_appetite.csv` contain 42 KRIs. CAP01 is computed in `kri_monthly` but excluded from risk score aggregation. |
| 2 | **SLSI**: 30-day net outflow of 8,750 as Sep-2026 anchor | Product-level run-off calculations only yielded 8,200. Other months use gross outflow × (8,750 / gross Sep-2026). |
| 3 | **3-month lookback** + event log from Oct-2024 | Ensures windowed KRIs (3-month delta, rolling 3/12-month counts, MoM) are defined from Oct-2025 onward. |
| 4 | Generator calibrated with **raking** and rolling-count allocation | Granular KRI data follows the value_start → value_target path; Sep-2026 score equals target_score. |
| 5 | **Full precision** for all calculations; ROUND_HALF_UP to 1 decimal only for ratings & display | Prevents floating-point drift in enterprise escalation rules (≥ 4.5 & weight ≥ 0.10). |
| 6 | KRI values rounded to **6 decimal places** (measurement precision) | Removes floating-point noise that would shift scores exactly at cut-points after stress. |
| 7 | Overrides scoped per period; delta carried through to all scenarios | §3.3: overrides must be consistent between monitoring and stress. |
| 8 | Trend requires 6 months of history; early warning uses 6-month OLS projecting 3 months ahead | §3.6: Oct-2025 to Feb-2026 is labelled *Insufficient history*. |
| 9 | Stress applied to engine KRI values; re-scoring delegated to `scoring.py` | No duplicated scoring logic between `stress.py` and `scoring.py`. |
| 10 | Management actions per **breach episode**; not repeated every month | §8.4: an action is created when a KRI first enters score 4, or escalates to score 5. |
| 11 | All stress coefficients in YAML | No magic numbers in Python — all parameters are auditable and changeable without touching code. |
| 12 | Power BI `.pbix` is not auto-generated | The dashboard is assembled manually following the detailed spec in `powerbi_spec.md`. |
| 13 | Regulatory mapping verified: Sharia governance → POJK 2/2024; LCR/NSFR for BUS → POJK 20/2025 | Spec §11: status must be verified before being cited. |

---

## Limitations

- **Out of scope (intentionally not built):** PD/LGD/EAD models, ECL/CKPN (PSAK 71), historical/Monte Carlo VaR, econometrics, machine learning, regulatory LCR/NSFR, and profit-sharing distribution models.
- **Static stress:** the balance sheet does not react and no management actions are modelled (gross impact). Non-macro KRIs (concentration, compliance, legal, some reputation) are treated as unchanged.
- **Analytical assumptions:** the 45% credit loss rate, transmission coefficients, weights, and cut-points are project assumptions — not calibrated against historical data.
- **Synthetic data:** some KRIs based on counts or small ratios only approximate the value_start at Oct-2025 due to integer granularity.
- **Power BI:** the `.pbix` file is not auto-generated; the dashboard is assembled manually following `dashboard/powerbi_spec.md`.
- **Regulatory mapping:** regulation statuses were verified as of 17-Sep-2026; they should be re-checked before being cited as regulations may change.

---

## Development Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Scaffolding, reference data, configuration | ✅ Complete |
| 2 | Synthetic data generator, validation.py | ✅ Complete |
| 3 | KRI engine, scoring, risk & enterprise profile | ✅ Complete |
| 4 | Stress testing (3 scenarios), capital overlay, waterfall, management actions | ✅ Complete |
| 5 | Excel framework, Power BI package, executive report, notebooks, regulatory mapping | ✅ Complete (final) |

---

## License

This project is licensed under the MIT License.

```
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

*This project was built for educational and portfolio purposes. PT Amanah Syariah Bank is a fictional entity.*
