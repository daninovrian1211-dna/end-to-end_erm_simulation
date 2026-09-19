"""Posisi valas → market_positions.csv. PDN = Σ |net position| / modal (MR01)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import MONTHLY_PERIODS

CURRENCIES = {"USD": (0.75, 1), "SAR": (0.15, 1), "SGD": (0.10, -1)}  # (porsi PDN, arah posisi)
FX_ASSETS_BASE = {"USD": 1450.0, "SAR": 260.0, "SGD": 180.0}          # asumsi sintetis, Rp miliar


def market_positions(core: pd.DataFrame, targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        pdn = targets["MR01"].iloc[t] / 100 * core.at[p, "equity"]
        for cur, (share, sign) in CURRENCIES.items():
            net = sign * share * pdn
            fx_a = FX_ASSETS_BASE[cur] * (1 + rng.normal(0, 0.03))
            off = round(rng.normal(0, 0.04) * fx_a, 6)
            fx_l = fx_a + off - net
            rows.append(dict(period=p, currency=cur, fx_assets=round(fx_a, 6), fx_liabilities=round(fx_l, 6),
                             off_balance=off, net_position=round(fx_a - fx_l + off, 6)))
    return pd.DataFrame(rows)
