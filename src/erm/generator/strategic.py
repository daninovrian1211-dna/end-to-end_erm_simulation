"""Strategic → strategic_monthly.csv. Growth pembiayaan di atas target (22% vs 15% pada Sep-2026)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import MONTHLY_PERIODS

INITIATIVES_TOTAL = 20


def strategic_monthly(targets: pd.DataFrame, profile: dict) -> pd.DataFrame:
    tgt = profile["financing"]["growth_target_yoy_pct"]
    rows = []
    for t, p in enumerate(MONTHLY_PERIODS):
        delayed = int(round(targets["ST04"].iloc[t] / 100 * INITIATIVES_TOTAL))
        rows.append(dict(period=p, financing_growth_yoy=round(tgt + targets["ST01"].iloc[t], 6),
                         financing_growth_target=float(tgt), cost_to_income=round(targets["ST03"].iloc[t], 6),
                         initiatives_total=INITIATIVES_TOTAL, initiatives_delayed=delayed))
    return pd.DataFrame(rows)
