"""Log insiden operasional → operational_events.csv.

Storyline: root cause dominan process failure pada operasi transaksi digital, lonjakan sejak Jun-2026."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import EVENT_PERIODS, LOOKBACK, MONTHLY_PERIODS, REPORTING_DATE, allocate_rolling, month_start

EVENT_TYPES = {  # Basel 7 kategori, probabilitas baseline
    "Internal Fraud": 0.04, "External Fraud": 0.12, "Employment Practices & Workplace Safety": 0.05,
    "Clients, Products & Business Practices": 0.12, "Damage to Physical Assets": 0.04,
    "Business Disruption & System Failures": 0.20, "Execution, Delivery & Process Management": 0.43,
}
ROOT_CAUSE_BY_TYPE = {
    "Internal Fraud": ["People"], "External Fraud": ["External event", "System failure"],
    "Employment Practices & Workplace Safety": ["People"], "Clients, Products & Business Practices": ["Process failure", "People"],
    "Damage to Physical Assets": ["External event"], "Business Disruption & System Failures": ["System failure", "Process failure"],
    "Execution, Delivery & Process Management": ["Process failure", "Process failure", "People"],
}
BUSINESS_UNITS = ["Digital Banking Operations", "Operasional Cabang", "Operasional Pembiayaan", "Treasury Operations",
                  "Teknologi Informasi", "Sumber Daya Manusia"]
CHANNELS = ["Mobile banking", "Internet banking", "Kantor cabang", "ATM", "Back office"]
SLA_DAYS = {"High": 3, "Medium": 7, "Low": 14}
BASELINE_MONTHLY = 13
SURGE_START = "2026-06"
# high-severity per bulan Okt-25..Sep-26 (rolling 3 bln: 1,1,1,1,1,2,1,2,2,3,3,3)
HIGH_REPORT = [1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1]
HIGH_LOOKBACK = [0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0]  # Okt-24..Sep-25
OFFSET = EVENT_PERIODS.index(MONTHLY_PERIODS[0])      # indeks event untuk Jul-2025


def operational_events(targets: pd.DataFrame, core: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ne = len(EVENT_PERIODS)
    rep0 = OFFSET + LOOKBACK  # indeks Okt-2025
    counts = np.r_[rng.integers(10, 14, rep0), targets["OR01"].to_numpy()[LOOKBACK:].astype(int)]
    high = np.array(HIGH_LOOKBACK + HIGH_REPORT)

    def rolling_target(kri):
        tgt = targets[kri].to_numpy()[LOOKBACK:] / 100
        n3 = np.array([counts[e - 2:e + 1].sum() for e in range(rep0, ne)])
        return tgt * n3

    rep_init = [int(round(0.04 * c)) for c in counts[:rep0]]
    repeats = np.r_[rep_init, allocate_rolling(rolling_target("OR04"), 3, rep_init[-2:], cap=counts[rep0:])]
    sla_init = [int(round(0.08 * c)) for c in counts[:rep0]]
    breaches = np.r_[sla_init, allocate_rolling(rolling_target("OR05"), 3, sla_init[-2:], cap=counts[rep0:])]

    # kerugian bersih bulanan agar rolling 12 bulan = OR03 × gross income TTM
    l12 = targets["OR03"].to_numpy() / 100 * core.gross_income_ttm.to_numpy()   # MONTHLY_PERIODS
    base_loss = l12[LOOKBACK] / 12
    loss = np.full(ne, base_loss)
    for e in range(rep0 + 1, ne):
        m = e - OFFSET
        loss[e] = l12[m] - l12[m - 1] + loss[e - 12]

    types, tp = list(EVENT_TYPES), np.array(list(EVENT_TYPES.values()))
    rows = []
    for e, period in enumerate(EVENT_PERIODS):
        n = int(counts[e])
        surge = n - BASELINE_MONTHLY if period >= SURGE_START and n > BASELINE_MONTHLY else 0
        et = rng.choice(types, n, p=tp)
        digital = np.zeros(n, bool)
        digital[:surge] = True
        et[digital] = "Execution, Delivery & Process Management"
        rc = np.array([rng.choice(ROOT_CAUSE_BY_TYPE[x]) for x in et])
        rc[digital] = "Process failure"
        bu = rng.choice(BUSINESS_UNITS, n, p=[0.30, 0.25, 0.18, 0.07, 0.15, 0.05])
        bu[digital] = "Digital Banking Operations"
        ch = rng.choice(CHANNELS, n, p=[0.30, 0.10, 0.30, 0.10, 0.20])
        ch[digital] = "Mobile banking"
        # severity: jumlah High dikunci; di bulan lonjakan High berasal dari insiden digital
        sev = np.where(rng.random(n) < 0.25, "Medium", "Low").astype(object)
        order = np.r_[np.where(digital)[0], rng.permutation(np.where(~digital)[0])] if surge else rng.permutation(n)
        sev[order[:high[e]]] = "High"
        wgt = np.select([sev == "High", sev == "Medium"], [25.0, 4.0], 1.0) * rng.lognormal(0, 0.5, n)
        net = wgt / wgt.sum() * loss[e]
        rr = np.where(sev == "High", rng.uniform(0, 0.15, n), rng.uniform(0, 0.30, n))
        gross = net / (1 - rr)
        rep = np.zeros(n, bool); rep[rng.permutation(n)[:repeats[e]]] = True
        brc = np.zeros(n, bool); brc[rng.permutation(n)[:breaches[e]]] = True
        sla = np.array([SLA_DAYS[s] for s in sev])
        start = month_start(period)
        days_in = start.days_in_month
        last_day = np.where(brc, days_in - sla - 1, days_in)
        day = 1 + (rng.random(n) * np.maximum(last_day, 1)).astype(int)
        date = start + pd.to_timedelta(day - 1, unit="D")
        res = np.where(brc, sla + rng.integers(1, 15, n), rng.integers(1, sla + 1))
        open_ = (date + pd.to_timedelta(res, unit="D")) > REPORTING_DATE
        for i in range(n):
            rows.append(dict(period=period, event_date=date[i].strftime("%Y-%m-%d"), event_type=et[i],
                             business_unit=bu[i], channel=ch[i], severity=sev[i], gross_loss=round(gross[i], 6),
                             recovery=round(gross[i] - net[i], 6), net_loss=round(net[i], 6), root_cause=rc[i],
                             repeat_flag=bool(rep[i]), sla_days=int(sla[i]),
                             resolution_days=np.nan if open_[i] else int(res[i]),
                             status="Open" if open_[i] else "Closed"))
    df = pd.DataFrame(rows).sort_values(["event_date", "event_type"], kind="mergesort", ignore_index=True)
    df.insert(0, "event_id", [f"OPE-{i+1:05d}" for i in range(len(df))])
    df["resolution_days"] = df["resolution_days"].astype("Int64")
    return df
