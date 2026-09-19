"""Likuiditas & pendanaan → deposits_monthly.csv, top_depositors.csv, maturity_profile.csv."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import MONTHLY_PERIODS

PRODUCTS = ["giro_wadiah", "tabungan", "deposito_mudharabah"]
BUCKETS = ["<=1m", "1-3m", "3-12m", ">12m"]
# benchmark pasar deposito (pp) dan tingkat indikatif giro/tabungan (asumsi sintetis)
DEPOSITO_BENCHMARK = (5.00, 5.15)
GIRO_RATE, GIRO_BENCH = 0.60, 0.80
TAB_RATE, TAB_BENCH = 1.60, 1.90


def deposits_monthly(core: pd.DataFrame, targets: pd.DataFrame, profile: dict, rng: np.random.Generator) -> pd.DataFrame:
    ro = profile["slsi"]["runoff_30d"]
    n = len(MONTHLY_PERIODS)
    bench = np.linspace(*DEPOSITO_BENCHMARK, n) + np.r_[rng.normal(0, 0.02, n - 1), 0]
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        dep_rate = bench[t] - targets["RR01"].iloc[t]
        spec = {"giro_wadiah": (GIRO_RATE, GIRO_BENCH), "tabungan": (TAB_RATE, TAB_BENCH),
                "deposito_mudharabah": (dep_rate, bench[t])}
        for prod in PRODUCTS:
            rows.append(dict(period=p, product=prod, balance=round(core.at[p, prod], 6),
                             equivalent_rate=round(spec[prod][0], 6), market_benchmark_rate=round(spec[prod][1], 6),
                             runoff_assumption=ro[prod]))
    return pd.DataFrame(rows)


def top_depositors(core: pd.DataFrame, targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    n_dep = 20
    base = np.sort(rng.pareto(1.6, n_dep) + 1)[::-1]
    products = np.array(["deposito_mudharabah"] * 13 + ["giro_wadiah"] * 6 + ["tabungan"])
    rng.shuffle(products[1:])
    ids = [f"DEP-{i+1:03d}" for i in range(n_dep)]
    drift = rng.normal(0, 0.03, (len(MONTHLY_PERIODS), n_dep))
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        w = base * np.exp(drift[t])
        total = targets["LQ03"].iloc[t] / 100 * core.at[p, "dpk"]
        bal = w / w.sum() * total
        rank = (-bal).argsort().argsort() + 1
        for i in range(n_dep):
            rows.append(dict(period=p, depositor_id=ids[i], product=products[i], balance=round(bal[i], 6), rank=int(rank[i])))
    return pd.DataFrame(rows).sort_values(["period", "rank"], ignore_index=True)


def total_assets(core: pd.DataFrame) -> pd.Series:
    return (core.gwm_required + core.excess_reserve + core.placements + core.sukuk_fvoci + core.sukuk_ac
            + core.gross_financing + core.allowance + core.other_assets)


def maturity_profile(core: pd.DataFrame, targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ta = total_assets(core)
    tl = ta - core.equity
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        A, L = ta[p], tl[p]
        gap1 = targets["LQ04"].iloc[t] / 100 * A          # negative maturity gap ≤1 bulan (absolut)
        a_sh = np.array([0.14, 0.10, 0.20]) + rng.normal(0, 0.003, 3)
        assets = np.r_[a_sh * A, 0.0]; assets[3] = A - assets[:3].sum()
        liab = np.array([assets[0] + gap1, 0.20 * L, 0.15 * L, 0.0]); liab[3] = L - liab[:3].sum()
        rsa = np.array([0.10, 0.08, 0.12, 0.35]) * A
        gap_rep = targets["MR03"].iloc[t] / 100 * A        # repricing gap ≤1 tahun (liability-sensitive)
        rsl_12 = rsa[:3].sum() + gap_rep
        rsl = np.r_[np.array([0.40, 0.35, 0.25]) * rsl_12, 0.20 * L]
        for b in range(4):
            rows.append(dict(period=p, bucket=BUCKETS[b], assets_maturing=round(assets[b], 6),
                             liabilities_maturing=round(liab[b], 6), rsa=round(rsa[b], 6), rsl=round(rsl[b], 6)))
    return pd.DataFrame(rows)
