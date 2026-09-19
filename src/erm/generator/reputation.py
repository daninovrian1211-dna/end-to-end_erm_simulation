"""Komplain & sentimen → complaints.csv, sentiment_monthly.csv.

Storyline: lonjakan komplain Ags–Sep 2026 terkait gangguan mobile banking."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import MONTHLY_PERIODS, REPORTING_DATE, month_start

BASE_COUNT_JUL25 = 470
CHANNELS = {"Mobile banking": 0.28, "Kantor cabang": 0.25, "Call center": 0.22, "Internet banking": 0.08,
            "ATM": 0.09, "Email / web": 0.08}
CATEGORIES = {"Gangguan transaksi mobile banking": 0.14, "Kegagalan transfer": 0.16, "Bagi hasil & biaya": 0.14,
              "Layanan petugas": 0.16, "Kartu ATM": 0.12, "Proses pembiayaan": 0.18, "Informasi produk": 0.10}
SLA_DAYS = {"Severe": 5, "Medium": 10, "Low": 15}
SURGE_START = "2026-08"


def complaint_counts(targets: pd.DataFrame) -> np.ndarray:
    counts = [BASE_COUNT_JUL25]
    for t in range(1, len(MONTHLY_PERIODS)):
        counts.append(int(round(counts[-1] * (1 + targets["RP01"].iloc[t] / 100))))
    return np.array(counts)


def complaints(targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    counts = complaint_counts(targets)
    ch_names, ch_p = list(CHANNELS), list(CHANNELS.values())
    cat_names, cat_p = list(CATEGORIES), list(CATEGORIES.values())
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        n = int(counts[t])
        # seluruh kenaikan di atas volume Jul-2026 berasal dari gangguan mobile banking
        surge = int(n - counts[MONTHLY_PERIODS.index(SURGE_START) - 1]) if p >= SURGE_START else 0
        ch = rng.choice(ch_names, n, p=ch_p)
        cat = rng.choice(cat_names, n, p=cat_p)
        ch[:surge] = "Mobile banking"
        cat[:surge] = "Gangguan transaksi mobile banking"
        n_severe = int(round(targets["RP02"].iloc[t] / 100 * n))
        n_breach = int(round(targets["RP03"].iloc[t] / 100 * n))
        sev = np.where(rng.random(n) < 0.30, "Medium", "Low").astype(object)
        sev[rng.permutation(n)[:n_severe]] = "Severe"
        sla = np.array([SLA_DAYS[s] for s in sev])
        brc = np.zeros(n, bool); brc[rng.permutation(n)[:n_breach]] = True
        start = month_start(p)
        horizon = (REPORTING_DATE - start).days + 1
        res = np.where(brc, sla + rng.integers(1, 20, n), rng.integers(1, sla + 1))
        # komplain melewati SLA dipastikan sudah selesai per reporting date (bulan terakhir: tanggal lebih awal)
        res = np.where(brc, np.minimum(res, np.maximum(horizon - 1, sla + 1)), res)
        last_day = np.where(brc, np.minimum(start.days_in_month, horizon - res), start.days_in_month)
        day = 1 + (rng.random(n) * np.maximum(last_day, 1)).astype(int)
        date = start + pd.to_timedelta(day - 1, unit="D")
        open_ = (date + pd.to_timedelta(res, unit="D")) > REPORTING_DATE
        rows.append(pd.DataFrame(dict(period=p, date=date, channel=ch, category=cat, severity=sev, sla_days=sla,
                                      resolution_days=np.where(open_, np.nan, res),
                                      status=np.where(open_, "Open", "Closed"))))
    df = pd.concat(rows, ignore_index=True).sort_values(["date", "channel", "category"], kind="mergesort", ignore_index=True)
    df.insert(0, "complaint_id", [f"CMPL-{i+1:06d}" for i in range(len(df))])
    df["resolution_days"] = df["resolution_days"].astype("Int64")
    return df.drop(columns="date")[["complaint_id", "period", "channel", "category", "severity", "sla_days",
                                    "resolution_days", "status"]]


def sentiment_monthly(targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        media = int(rng.integers(300, 380))
        sosmed = int(rng.integers(2300, 2700) * (1.4 if p >= SURGE_START else 1.0))
        total_neg = int(round(targets["RP04"].iloc[t] / 100 * (media + sosmed)))
        neg_media = int(round(total_neg * 0.08))
        rows.append(dict(period=p, source="media", mentions=media, negative_mentions=neg_media))
        rows.append(dict(period=p, source="sosmed", mentions=sosmed, negative_mentions=total_neg - neg_media))
    return pd.DataFrame(rows)
