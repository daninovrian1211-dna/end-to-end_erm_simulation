"""Management action otomatis (spec §8.4).

Aturan: setiap KRI dengan skor ≥ 4 menghasilkan action. Skor 4 → jatuh tempo 30 hari; skor 5 → 14 hari
dan eskalasi ke Direksi/RMC. Teks action diambil dari action_library.csv (tidak dikarang bebas).
Satu action dibuat saat KRI pertama kali masuk skor 4 atau naik ke skor 5 (episode breach), bukan setiap bulan."""
from __future__ import annotations

import pandas as pd

from . import scoring

DUE_DAYS = {4: 30, 5: 14}
SEVERITY = {4: "Tolerance breach", 5: "Limit breach"}
TRIGGER = {4: "KRI score = 4 → action 30 hari",
           5: "KRI score = 5 → action 14 hari + eskalasi Direksi/RMC"}


def _fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def generate_actions(kri_monthly: pd.DataFrame, reporting_date: str = "2026-09-30",
                     ref_dir=scoring.REF_DIR) -> pd.DataFrame:
    lib = pd.read_csv(ref_dir / "action_library.csv").set_index("kri_id")
    ra = pd.read_csv(ref_dir / "risk_appetite.csv").set_index("kri_id")
    rep = pd.Timestamp(reporting_date)
    k = kri_monthly[kri_monthly.risk_type != scoring.CAPITAL_OVERLAY].sort_values(["kri_id", "period"])
    rows = []
    for kid, g in k.groupby("kri_id", sort=True):
        scores = g.score.astype(int).tolist()
        periods = g.period.tolist()
        values = g.value.tolist()
        for i, sc in enumerate(scores):
            prev = scores[i - 1] if i else 0
            triggered = (sc >= 4 and prev < 4) or (sc == 5 and prev == 4)
            if not triggered:
                continue
            level = 5 if sc == 5 else 4
            # episode berakhir saat skor kembali < 4, atau digantikan eskalasi ke skor 5
            end = next((j for j in range(i + 1, len(scores))
                        if scores[j] < 4 or (level == 4 and scores[j] == 5)), None)
            created = pd.Period(periods[i], freq="M").end_time.normalize()
            due = created + pd.Timedelta(days=DUE_DAYS[level])
            if end is not None:
                status = "Closed" if scores[end] < 4 else "Superseded (eskalasi skor 5)"
            else:
                status = "Overdue" if due < rep else "Open"
            r = ra.loc[kid]
            limit_txt = f"trigger {_fmt(r.c3)}, limit {_fmt(r.c4)}"
            rows.append(dict(period=periods[i], risk_type=r.risk_type, kri_id=kid,
                             finding=f"{r.kri_name}: {_fmt(values[i])} {r.unit} (skor {sc}, {SEVERITY[level]}; {limit_txt})",
                             severity=SEVERITY[level], recommended_action=lib.at[kid, "recommended_action"],
                             owner=lib.at[kid, "action_owner"], due_date=due.strftime("%Y-%m-%d"), status=status,
                             trigger_rule=TRIGGER[level]))
    df = pd.DataFrame(rows, columns=["period", "risk_type", "kri_id", "finding", "severity", "recommended_action",
                                     "owner", "due_date", "status", "trigger_rule"])
    df = df.sort_values(["period", "kri_id"], ignore_index=True)
    df.insert(0, "action_id", [f"ACT-{i+1:04d}" for i in range(len(df))])
    return df
