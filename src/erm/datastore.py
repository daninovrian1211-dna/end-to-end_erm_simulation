"""Akses terpusat ke output engine (data/output) dan register referensi (data/reference).

Excel, paket Power BI, dan executive report hanya membaca angka melalui modul ini."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "data" / "output"
REF_DIR = ROOT / "data" / "reference"
CONFIG_DIR = ROOT / "config"

OUTPUT_FILES = ["kri_monthly", "risk_scores_monthly", "enterprise_profile_monthly", "stress_results",
                "stress_risk_scores", "stress_enterprise_summary", "stress_waterfall", "capital_overlay",
                "management_actions"]
REFERENCE_FILES = ["risk_appetite", "risk_weights", "macro_scenarios", "judgment_overrides",
                   "interdependency_edges", "emerging_risks", "action_library"]
SCENARIOS = ["baseline", "adverse", "severe"]


def load_outputs(out_dir: Path | str = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    out_dir = Path(out_dir)
    return {n: pd.read_csv(out_dir / f"{n}.csv") for n in OUTPUT_FILES}


def load_reference(ref_dir: Path | str = REF_DIR) -> dict[str, pd.DataFrame]:
    ref_dir = Path(ref_dir)
    return {n: pd.read_csv(ref_dir / f"{n}.csv") for n in REFERENCE_FILES}


def load_config() -> dict[str, dict]:
    return {n: yaml.safe_load((CONFIG_DIR / f"{n}.yaml").read_text(encoding="utf-8"))
            for n in ("bank_profile", "stress_parameters")}


def reporting_period() -> str:
    return load_config()["bank_profile"]["reporting"]["period_end"]
