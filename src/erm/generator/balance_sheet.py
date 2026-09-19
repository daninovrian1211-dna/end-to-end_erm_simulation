"""Neraca jangkar Sep-2026 (§2) diturunkan mundur → balance_sheet_monthly.csv, capital_monthly.csv.

Agregat inti (pembiayaan, DPK, ekuitas, likuiditas) dibangun di sini dan menjadi kontrol total
bagi seluruh data granular."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import LOOKBACK, MONTHLY_PERIODS

BUDGET_ANNUAL = {"2025": 880.0, "2026": 1000.0}  # RKB laba bersih tahunan (asumsi sintetis)
GI_TTM_START = 4950.0                           # gross income TTM Jul-2025 (asumsi sintetis)
# bobot distribusi pertumbuhan pembiayaan Okt-25..Sep-26: melambat saat likuiditas mengetat
OTHER_FUNDING_START = 3000.0                     # pendanaan lain Jul-2025 (asumsi sintetis)
OTHER_FUNDING_LAMBDA = 0.5
FIN_GROWTH_WEIGHTS = np.array([1.30, 1.30, 1.25, 1.25, 1.20, 1.20, 1.15, 1.10, 0.60, 0.50, 0.40, 0.35])


def financing_path(profile: dict, growth_yoy_sep: float) -> np.ndarray:
    f_sep = profile["balance_sheet_2026_09"]["assets"]["gross_financing"]
    f_sep_prev = f_sep / (1 + growth_yoy_sep / 100)       # Sep-2025 konsisten dengan growth 22%
    logs = np.log(f_sep / f_sep_prev) * FIN_GROWTH_WEIGHTS / FIN_GROWTH_WEIGHTS.sum()
    f = np.empty(len(MONTHLY_PERIODS))
    f[LOOKBACK - 1] = f_sep_prev
    for i, g in enumerate(logs):
        f[LOOKBACK + i] = f[LOOKBACK + i - 1] * np.exp(g)
    f[1] = f[2] / 1.017
    f[0] = f[1] / 1.017
    f[-1] = f_sep
    return f


def dpk_path(profile: dict, fin: np.ndarray, targets: pd.DataFrame) -> np.ndarray:
    """DPK: FDR Okt-25 dan LQ05 (Okt-25, Sep-26) sebagai jangkar; puncak Mei-2026, turun Jun–Sep 2026."""
    d_sep = profile["balance_sheet_2026_09"]["liabilities_equity"]["total_dpk"]
    ra_start_fdr = targets["LQ02"].iloc[LOOKBACK]
    lq05_start, lq05_sep = targets["LQ05"].iloc[LOOKBACK], targets["LQ05"].iloc[-1]
    d = np.empty(len(MONTHLY_PERIODS))
    i_oct, i_apr, i_may, i_jun = LOOKBACK, LOOKBACK + 6, LOOKBACK + 7, LOOKBACK + 8
    d[i_oct] = fin[i_oct] / (ra_start_fdr / 100)
    d[0] = d[i_oct] / (1 - lq05_start / 100)
    d[1], d[2] = d[0] * 0.997, d[0] * 0.993
    d[i_jun] = d_sep / (1 - lq05_sep / 100)
    d[i_may] = d[i_jun] * 1.004
    d[i_apr] = d[i_may] / 1.008
    g = (d[i_apr] / d[i_oct]) ** (1 / (i_apr - i_oct))
    for t in range(i_oct + 1, i_apr):
        d[t] = d[t - 1] * g
    d[-1] = d_sep
    d[-2] = d_sep + (d[i_jun] - d_sep) * 0.35   # Ags
    d[-3] = d_sep + (d[i_jun] - d_sep) * 0.70   # Jul
    return d


def build_core(profile: dict, targets: pd.DataFrame, carry: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    bs = profile["balance_sheet_2026_09"]
    a, le = bs["assets"], bs["liabilities_equity"]
    sl = profile["slsi"]
    n = len(MONTHLY_PERIODS)
    growth_sep = 15 + targets["ST01"].iloc[-1]
    fin = financing_path(profile, growth_sep)
    dpk = dpk_path(profile, fin, targets)

    # komposisi DPK (share Sep-2026) dengan noise kecil, Sep persis
    shares_sep = np.array([le["giro_wadiah"], le["tabungan"], le["deposito_mudharabah"]]) / le["total_dpk"]
    noise = rng.normal(0, 0.003, (n, 3))
    noise -= noise.mean(axis=1, keepdims=True)
    noise[-1] = 0
    shares = shares_sep + noise
    prod = shares * dpk[:, None]

    # laba & ekuitas (mundur dari ekuitas Sep-2026)
    years = np.array([p[:4] for p in MONTHLY_PERIODS])
    months = np.array([int(p[5:]) for p in MONTHLY_PERIODS])
    budget_ytd = np.array([BUDGET_ANNUAL[y] * m / 12 for y, m in zip(years, months)])
    profit_ytd = budget_ytd * targets["ST02"].to_numpy() / 100
    monthly_profit = np.where(months == 1, profit_ytd, profit_ytd - np.roll(profit_ytd, 1))
    equity = np.empty(n)
    equity[-1] = le["equity"]
    for t in range(n - 2, -1, -1):
        equity[t] = equity[t + 1] - monthly_profit[t + 1]

    gi = np.linspace(GI_TTM_START, profile["income"]["gross_income_annual"], n)
    kpmm = targets["CAP01"].to_numpy()
    atmr = equity / (kpmm / 100)

    gwm = dpk * a["cash_and_bi_detail"]["reserve_requirement_gwm"] / le["total_dpk"]
    allowance = np.full(n, float(a["allowance_for_losses"]))
    other_assets = np.full(n, float(a["other_assets"]))
    other_liab = np.full(n, float(le["other_liabilities"]))
    sukuk = (carry.fvoci + carry.ac).to_numpy()
    unenc = carry.unencumbered.to_numpy()

    r = sl["runoff_30d"]
    dep_runoff = prod @ np.array([r["giro_wadiah"], r["tabungan"], r["deposito_mudharabah"]])
    gross_sep = dep_runoff[-1] + r["other_funding"] * le["other_funding"]
    k = sl["net_outflow_30d_anchor"] / gross_sep
    s = targets["LQ01"].to_numpy() / 100
    haircut = 1 - sl["haircut_sukuk_unencumbered"]

    # Solve (1): pendanaan lain (Fo) dan aset likuid (L) yang memenuhi SLSI + neraca seimbang
    a0 = fin + allowance + sukuk + gwm + other_assets
    c = dpk + other_liab + equity - a0 + haircut * unenc
    fo_solved = (s * k * dep_runoff - c) / (1 - r["other_funding"] * s * k)
    # (2) Untuk menghindari ayunan pendanaan lain yang ekstrem, separuh penyesuaian dialihkan ke aset lain.
    fo_smooth = np.linspace(OTHER_FUNDING_START, le["other_funding"], n)
    fo = OTHER_FUNDING_LAMBDA * fo_solved + (1 - OTHER_FUNDING_LAMBDA) * fo_smooth
    fo[-1] = le["other_funding"]
    liquid = s * k * (dep_runoff + r["other_funding"] * fo) - haircut * unenc
    other_assets = dpk + fo + other_liab + equity - (fin + allowance + sukuk + gwm + liquid)
    split = a["cash_and_bi_detail"]["excess_reserve"] / (a["cash_and_bi_detail"]["excess_reserve"] + a["placements_with_other_banks"])

    core = pd.DataFrame(dict(
        gross_financing=fin, dpk=dpk, giro_wadiah=prod[:, 0], tabungan=prod[:, 1], deposito_mudharabah=prod[:, 2],
        equity=equity, profit_ytd=profit_ytd, profit_budget_ytd=budget_ytd, gross_income_ttm=gi, atmr=atmr,
        gwm_required=gwm, excess_reserve=liquid * split, placements=liquid * (1 - split),
        sukuk_fvoci=carry.fvoci.to_numpy(), sukuk_ac=carry.ac.to_numpy(), unencumbered=unenc,
        allowance=allowance, other_assets=other_assets, other_funding=fo, other_liabilities=other_liab,
        dep_runoff=dep_runoff, net_outflow_k=k), index=pd.Index(MONTHLY_PERIODS, name="period"))
    if (fo <= 0).any() or (liquid <= 0).any() or (other_assets <= 0).any():
        raise ValueError("kalibrasi neraca menghasilkan pendanaan lain / aset likuid non-positif")
    return core


LINES = [  # (line_item, category, sub_category, kolom core)
    ("kas_giro_bi_gwm_wajib", "asset", "kas_giro_bi", "gwm_required"),
    ("kas_giro_bi_excess", "asset", "kas_giro_bi", "excess_reserve"),
    ("penempatan_bank_lain", "asset", "penempatan", "placements"),
    ("sukuk_fvoci", "asset", "sukuk", "sukuk_fvoci"),
    ("sukuk_amortized_cost", "asset", "sukuk", "sukuk_ac"),
    ("pembiayaan_bruto", "asset", "pembiayaan", "gross_financing"),
    ("cadangan_kerugian", "asset", "cadangan", "allowance"),
    ("aset_lain", "asset", "aset_lain", "other_assets"),
    ("giro_wadiah", "liability", "dpk", "giro_wadiah"),
    ("tabungan", "liability", "dpk", "tabungan"),
    ("deposito_mudharabah", "liability", "dpk", "deposito_mudharabah"),
    ("pendanaan_lain", "liability", "pendanaan_lain", "other_funding"),
    ("liabilitas_lain", "liability", "liabilitas_lain", "other_liabilities"),
    ("ekuitas", "equity", "ekuitas", "equity"),
]


def balance_sheet_monthly(core: pd.DataFrame) -> pd.DataFrame:
    rows = [dict(period=p, line_item=li, category=cat, sub_category=sub, amount=round(core.at[p, col], 6))
            for p in core.index for li, cat, sub, col in LINES]
    return pd.DataFrame(rows)


def capital_monthly(core: pd.DataFrame) -> pd.DataFrame:
    df = core[["equity", "atmr", "gross_income_ttm", "profit_ytd", "profit_budget_ytd"]].rename(
        columns={"equity": "capital_kpmm"}).round(6).reset_index()
    return df
