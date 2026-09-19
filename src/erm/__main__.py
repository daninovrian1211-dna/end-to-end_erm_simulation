"""CLI ERM.

    python -m erm engine   [--raw data/raw] [--out data/output]   # KRI, skoring, stress, capital, actions
    python -m erm excel                                            # excel/ERM_Framework.xlsx
    python -m erm powerbi                                          # dashboard/model/*.csv
    python -m erm report                                           # report/ERM_Executive_Report.pdf

Urutan: nilai KRI dari data raw → skoring bulanan → stress 3 skenario → capital overlay → management action."""
import argparse
from pathlib import Path

import pandas as pd
import yaml

from . import actions, capital, kri, scoring, stress

ROOT = Path(__file__).resolve().parents[2]


def run_engine(raw_dir: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = yaml.safe_load((ROOT / "config" / "bank_profile.yaml").read_text(encoding="utf-8"))
    period = profile["reporting"]["period_end"]
    result = scoring.run_scoring(kri.build_kri_monthly(raw_dir))

    growth = pd.read_csv(Path(raw_dir) / "strategic_monthly.csv").set_index("period").at[period, "financing_growth_yoy"]
    st = stress.run_stress(result["kri_monthly"], float(growth), period)
    cap = capital.capital_overlay(st["stress_results"])
    # CAP01 pada stress_results diisi KPMM hasil capital overlay (bukan bagian risk score)
    kpmm = cap.set_index("scenario").kpmm.to_dict()
    sr = st["stress_results"]
    mask = sr.kri_id == "CAP01"
    sr.loc[mask, "stressed_value"] = sr.loc[mask, "scenario"].map(kpmm)
    sr.loc[mask, "stressed_score"] = sr.loc[mask, "scenario"].map(cap.set_index("scenario").cap_score)

    result.update(st)
    result["capital_overlay"] = cap
    result["management_actions"] = actions.generate_actions(result["kri_monthly"], profile["reporting"]["reporting_date"])
    for name, df in result.items():
        df.to_csv(out_dir / f"{name}.csv", index=False, lineterminator="\n")
    return result


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m erm")
    p.add_argument("command", choices=["engine", "excel", "powerbi", "report"])
    p.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    p.add_argument("--out", default=str(ROOT / "data" / "output"))
    a = p.parse_args()
    if a.command == "excel":
        from . import excel_framework
        print(excel_framework.build())
        return
    if a.command == "powerbi":
        from . import export_powerbi
        for path in export_powerbi.export():
            print(path)
        return
    if a.command == "report":
        from . import report
        print(report.build())
        return
    res = run_engine(Path(a.raw), Path(a.out))
    period = res["enterprise_profile_monthly"].period.max()
    print(scoring.profile_table(res["risk_scores_monthly"], res["enterprise_profile_monthly"], period).to_string(index=False))


if __name__ == "__main__":
    main()
