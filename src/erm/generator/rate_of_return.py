"""Rate of return & displaced commercial risk → rate_of_return_monthly.csv."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import MONTHLY_PERIODS


def rate_of_return_monthly(deposits: pd.DataFrame, targets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    n = len(MONTHLY_PERIODS)
    dep = deposits[deposits["product"] == "deposito_mudharabah"].set_index("period")
    fin_yield = np.linspace(10.6, 10.3, n) + np.r_[rng.normal(0, 0.03, n - 1), 0]
    nisbah = np.linspace(45.0, 42.0, n) + np.r_[rng.normal(0, 0.2, n - 1), 0]
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        actual = dep.at[p, "equivalent_rate"]  # realisasi imbal hasil deposan = equivalent rate deposito
        rows.append(dict(period=p, financing_yield=round(fin_yield[t], 6),
                         expected_depositor_return=round(actual + targets["RR02"].iloc[t], 6),
                         actual_depositor_return=round(actual, 6),
                         profit_distribution_ratio=round(nisbah[t], 6), nim=round(targets["RR03"].iloc[t], 6)))
    return pd.DataFrame(rows)
