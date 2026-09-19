"""Pelanggaran kepatuhan & temuan DPS → compliance_events.csv.

Storyline: pada Sep-2026 ada 3 pelanggaran high-severity yang melewati target remediasi;
2 di antaranya terkait akad pembiayaan yang belum sesuai opini DPS."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import EVENT_PERIODS, LOOKBACK, MONTHLY_PERIODS, allocate_rolling, month_end, month_start

AKAD_DPS_REF = "Kepatuhan syariah: akad pembiayaan belum sesuai opini DPS"
REFS_REGULATOR = ["Ketentuan pelaporan bank kepada otoritas", "Ketentuan APU-PPT", "Ketentuan perlindungan konsumen",
                  "Ketentuan manajemen risiko TI", "Ketentuan transparansi produk"]
REFS_DPS = ["Kepatuhan syariah: dokumentasi akad", "Kepatuhan syariah: penggunaan dana kebajikan",
            "Kepatuhan syariah: perhitungan bagi hasil"]
UNITS = ["Pembiayaan UMKM", "Pembiayaan Korporasi", "Digital Banking", "Treasury", "Operasional Cabang", "Funding"]

# Event naratif (dikunci): (id, period, source, ref, severity, unit, target, closed)
NARRATIVE = [
    ("H1", "2025-07", "internal audit", "Ketentuan APU-PPT", "High", "Operasional Cabang", "2025-10-10", "2026-01-20"),
    ("H2", "2025-10", "regulator", "Ketentuan pelaporan bank kepada otoritas", "High", "Funding", "2025-12-31", None),
    ("H6", "2025-11", "internal audit", "Ketentuan manajemen risiko TI", "High", "Digital Banking", "2026-01-15", "2026-06-10"),
    ("D0", "2025-05", "DPS", "Kepatuhan syariah: dokumentasi akad", "Medium", "Pembiayaan Korporasi", "2025-08-31", "2026-06-05"),
    ("H4", "2026-03", "DPS", AKAD_DPS_REF + " (murabahah UMKM)", "High", "Pembiayaan UMKM", "2026-06-15", None),
    ("H5", "2026-05", "DPS", AKAD_DPS_REF + " (musyarakah korporasi)", "High", "Pembiayaan Korporasi", "2026-07-31", None),
]
# jumlah pelanggaran regulasi (regulator + internal audit) per bulan Okt-24..Sep-25
NON_DPS_LOOKBACK = [1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 0]
CP03_WINDOW = 12


def compliance_events(targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ne = len(EVENT_PERIODS)
    off = EVENT_PERIODS.index(MONTHLY_PERIODS[LOOKBACK])  # indeks Okt-2025
    narrative_non_dps = pd.Series([p for _, p, s, *_ in NARRATIVE if s != "DPS"]).value_counts()

    cp01 = targets["CP01"].to_numpy()[LOOKBACK:]
    non_dps = np.r_[NON_DPS_LOOKBACK, allocate_rolling(cp01, 3, NON_DPS_LOOKBACK[-2:])]
    for p, c in narrative_non_dps.items():            # pastikan event naratif tercakup dalam count
        e = EVENT_PERIODS.index(p)
        if non_dps[e] < c:
            raise ValueError(f"count pelanggaran {p} lebih kecil dari event naratif")

    rows = []
    for key, p, src, ref, sev, unit, tgt, closed in NARRATIVE:
        rows.append(dict(key=key, period=p, source=src, regulation_ref=ref, severity=sev, business_unit=unit,
                         target_remediation_date=tgt, closed_date=closed))
    for e, p in enumerate(EVENT_PERIODS):
        n_generic = int(non_dps[e] - narrative_non_dps.get(p, 0))
        # temuan DPS rutin (severity rendah, ditutup < 60 hari) setiap kuartal
        n_dps = 1 if int(p[5:]) % 3 == 2 else 0
        for k in range(n_generic + n_dps):
            is_dps = k >= n_generic
            start = month_start(p)
            date = start + pd.Timedelta(days=int(rng.integers(0, 25)))
            sev = "Low" if is_dps else rng.choice(["Low", "Medium"], p=[0.55, 0.45])
            target = date + pd.Timedelta(days=int(rng.integers(30, 60)))
            close = target - pd.Timedelta(days=int(rng.integers(1, 20)))  # generik: selesai sebelum target
            rows.append(dict(key=None, period=p, source="DPS" if is_dps else rng.choice(["regulator", "internal audit"], p=[0.4, 0.6]),
                             regulation_ref=rng.choice(REFS_DPS if is_dps else REFS_REGULATOR), severity=sev,
                             business_unit=rng.choice(UNITS), target_remediation_date=target.strftime("%Y-%m-%d"),
                             closed_date=close.strftime("%Y-%m-%d") if close <= pd.Timestamp("2026-09-30") else None))
    df = pd.DataFrame(rows)
    df["_order"] = df.period + df.target_remediation_date
    df = df.sort_values(["_order", "regulation_ref"], kind="mergesort", ignore_index=True).drop(columns="_order")

    # repeat flag: rasio repeat rolling 12 bulan (seluruh event) mengikuti CP03
    counts = df.groupby("period").size().reindex(EVENT_PERIODS, fill_value=0).to_numpy()
    init = [0] * (CP03_WINDOW - 1)
    tgt = []
    for e in range(off, ne):
        tgt.append(targets["CP03"].to_numpy()[e - off + LOOKBACK] / 100 * counts[e - CP03_WINDOW + 1:e + 1].sum())
    head = [int(round(0.08 * c)) for c in counts[:off]]
    rep_counts = np.r_[head, allocate_rolling(np.array(tgt), CP03_WINDOW, head[-(CP03_WINDOW - 1):], cap=counts[off:])]
    df["repeat_flag"] = False
    for e, p in enumerate(EVENT_PERIODS):
        idx = df.index[(df.period == p) & df.key.isna()]
        if len(idx) == 0:
            idx = df.index[df.period == p]
        pick = rng.permutation(idx)[:min(rep_counts[e], len(idx))]
        df.loc[pick, "repeat_flag"] = True

    df["status"] = np.where(df.closed_date.isna(), "Open", "Closed")
    df.insert(0, "breach_id", [f"CMP-{i+1:04d}" for i in range(len(df))])
    return df[["breach_id", "period", "source", "regulation_ref", "severity", "business_unit",
               "target_remediation_date", "closed_date", "repeat_flag", "status"]]
