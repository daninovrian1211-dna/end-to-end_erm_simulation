"""Kasus hukum → legal_cases.csv.

Portofolio kecil yang dirancang per kasus: kasus terbuka 7 → 8, satu kasus high-risk,
potensi eksposur 0,7% → 0,8% modal, aging >365 hari 1/7 → 2/8."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import LOOKBACK

# (key, open_period, case_type, counterparty_type, severity, bobot eksposur, closed_period)
CASES = [
    ("A", "2024-06", "Wanprestasi pembiayaan", "Nasabah korporasi", "High", None, None),
    ("B", "2025-08", "Sengketa eksekusi agunan", "Nasabah UMKM", "Medium", None, None),
    ("C", "2025-10", "Gugatan perbuatan melawan hukum", "Nasabah ritel", "Low", None, None),
    ("D", "2025-10", "Sengketa ketenagakerjaan", "Karyawan", "Low", None, None),
    ("E", "2025-10", "Sengketa kontrak vendor", "Vendor", "Low", None, None),
    ("F", "2025-03", "Sengketa akad musyarakah", "Nasabah korporasi", "Medium", None, "2026-01"),
    ("G", "2025-06", "Gugatan nasabah dana pihak ketiga", "Nasabah ritel", "Low", None, "2026-03"),
    ("H", "2026-01", "Sengketa eksekusi agunan", "Nasabah korporasi", "Medium", None, None),
    ("I", "2026-03", "Gugatan perlindungan konsumen", "Nasabah ritel", "Low", None, None),
    ("J", "2026-04", "Sengketa pembiayaan sindikasi", "Bank lain", "Medium", None, None),
    ("K", "2023-11", "Sengketa sewa kantor cabang", "Vendor", "Low", None, "2025-08"),
]
BASE_WEIGHT = {"A": 18, "B": 4, "C": 3, "D": 3, "E": 2, "F": 8, "G": 5, "H": 12, "I": 8, "J": 6, "K": 3}


def legal_cases(targets: pd.DataFrame, core: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Potensi kerugian diskalakan agar Σ eksposur kasus terbuka = LG03 × modal pada Okt-2025 dan Sep-2026."""
    cap_oct, cap_sep = core.equity.iloc[LOOKBACK], core.equity.iloc[-1]
    ex_oct = targets["LG03"].iloc[LOOKBACK] / 100 * cap_oct
    ex_sep = targets["LG03"].iloc[-1] / 100 * cap_sep
    common = ["A", "B", "C", "D", "E"]
    w = {k: v * rng.uniform(0.9, 1.1) for k, v in BASE_WEIGHT.items()}
    common_sum = sum(w[k] for k in common)
    loss = {k: w[k] for k in common}
    oct_only, sep_only = ["F", "G"], ["H", "I", "J"]
    for grp, total in ((oct_only, ex_oct - common_sum), (sep_only, ex_sep - common_sum)):
        s = sum(w[k] for k in grp)
        for k in grp:
            loss[k] = w[k] / s * total
    loss["K"] = w["K"]
    rows = []
    for i, (key, op, ctype, cpty, sev, _, closed) in enumerate(sorted(CASES, key=lambda c: c[1])):
        rows.append(dict(case_id=f"LGL-{i+1:03d}", open_period=op, case_type=ctype, counterparty_type=cpty,
                         severity=sev, potential_loss=round(loss[key], 6), provisioned_flag=sev == "High",
                         status="Closed" if closed else "Open", closed_period=closed))
    return pd.DataFrame(rows)
