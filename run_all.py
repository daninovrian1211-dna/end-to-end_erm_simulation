"""Menjalankan seluruh pipeline tanpa `make` (cocok untuk Windows).

    python run_all.py            # data → engine → Excel → Power BI → report → test
    python run_all.py --no-test  # tanpa menjalankan test
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def step(title, fn):
    print(f"\n=== {title} ===", flush=True)
    result = fn()
    if result is not None:
        print(result)


def main() -> int:
    from erm import excel_framework, export_powerbi, report
    from erm.__main__ import run_engine
    from erm.generator import generate_all

    step("1/5 Membuat data sintetis (data/raw)", lambda: f"{len(generate_all())} file dibuat")
    step("2/5 Menjalankan engine (data/output)", lambda: f"{len(run_engine(ROOT / 'data' / 'raw', ROOT / 'data' / 'output'))} file dibuat")
    step("3/5 Membuat Excel framework", excel_framework.build)
    step("4/5 Membuat paket Power BI", lambda: f"{len(export_powerbi.export())} tabel dibuat")
    step("5/5 Membuat executive report", report.build)
    if "--no-test" in sys.argv:
        return 0
    print("\n=== Menjalankan pemeriksaan otomatis (pytest) ===", flush=True)
    return subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
