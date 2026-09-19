"""Portofolio sukuk (FVOCI & amortized cost) → investment_portfolio.csv.

Desain: set holding tetap selama periode (tanpa jual-beli). Harga FVOCI mengikuti indeks yang
dikalibrasi ke IV03; modified duration per holding direkalibrasi bulanan agar MR02 dan IV04
mengikuti jalur target (dokumentasi: data sintetis)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import LOOKBACK, MONTHLY_PERIODS, REPORTING_DATE

CORP_ISSUERS = ["PT Sukuk Energi Nusantara (fiktif)", "PT Infrastruktur Jalan Syariah (fiktif)",
                "PT Telekomunikasi Madani (fiktif)", "PT Perkebunan Hijau Lestari (fiktif)",
                "PT Semen Andalas Syariah (fiktif)", "PT Pembiayaan Multiguna Amanah (fiktif)"]
BELOW_IDA = ["idA-(sy)", "idBBB+(sy)", "idBBB(sy)", "idBBB-(sy)"]


def price_index(targets: pd.DataFrame) -> np.ndarray:
    """Indeks harga FVOCI: idx_t = idx_{t-3} × (1 − IV03_t/100)."""
    iv03 = targets["IV03"].to_numpy()
    idx = np.ones(len(MONTHLY_PERIODS))
    idx[:LOOKBACK] = [1.0, 0.9985, 0.9970]
    for t in range(LOOKBACK, len(idx)):
        idx[t] = idx[t - 3] * (1 - iv03[t] / 100)
    return idx / idx[-1]  # normalisasi: indeks Sep-2026 = 1


def build_holdings(targets: pd.DataFrame, profile: dict, rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray]:
    sd = profile["balance_sheet_2026_09"]["assets"]["sukuk_detail"]
    idx = price_index(targets)
    rows = []
    # Amortized cost: SBSN tenor panjang; 3 seri dijaminkan (repo) total 3.000
    ac_faces = np.array([1200, 1000, 800, 450, 350, 200])
    for i, face in enumerate(ac_faces):
        rows.append(dict(holding_id=f"INV-AC-{i+1:02d}", issuer="Pemerintah RI (SBSN)", issuer_type="sovereign",
                         instrument="SBSN", classification="AC", rating="idAAA(sy)", face=float(face),
                         md_base=rng.uniform(6.0, 8.5), price_eps=rng.normal(0, 0.01), encumbered=i < 3))
    ac = pd.DataFrame(rows)
    ac_mv_sep = float((ac.face * (1 + ac.price_eps)).sum())  # indeks Sep = 1
    total_mv_sep = sd["fvoci"] + ac_mv_sep

    fv = []
    # issuer non-sovereign terbesar (IV01) dan eksposur di bawah idA (IV02) — share MV konstan
    iv01 = targets["IV01"].iloc[-1] / 100 * total_mv_sep
    iv02 = targets["IV02"].iloc[-1] / 100 * total_mv_sep
    fv += [dict(issuer=CORP_ISSUERS[0], rating="idAA+(sy)", mv=iv01 * 0.6),
           dict(issuer=CORP_ISSUERS[0], rating="idAA(sy)", mv=iv01 * 0.4),
           dict(issuer=CORP_ISSUERS[4], rating="idA-(sy)", mv=iv02 * 0.65),
           dict(issuer=CORP_ISSUERS[5], rating="idBBB+(sy)", mv=iv02 * 0.35)]
    other_corp = [(CORP_ISSUERS[1], "idAAA(sy)"), (CORP_ISSUERS[2], "idAA(sy)"), (CORP_ISSUERS[3], "idA(sy)")]
    corp_w = rng.uniform(0.8, 1.2, len(other_corp))
    corp_total = 0.12 * sd["fvoci"]
    for (iss, rt), w in zip(other_corp, corp_w / corp_w.sum()):
        fv.append(dict(issuer=iss, rating=rt, mv=corp_total * w))
    n_sbsn = 12
    sbsn_w = rng.dirichlet(np.full(n_sbsn, 4.0))
    sbsn_total = sd["fvoci"] - sum(h["mv"] for h in fv)
    for w in sbsn_w:
        fv.append(dict(issuer="Pemerintah RI (SBSN)", rating="idAAA(sy)", mv=sbsn_total * w))
    for i, h in enumerate(fv):
        sov = h["issuer"].startswith("Pemerintah")
        eps = rng.normal(0, 0.01)
        rows.append(dict(holding_id=f"INV-FV-{i+1:02d}", issuer=h["issuer"],
                         issuer_type="sovereign" if sov else "corporate",
                         instrument="SBSN" if sov else "Sukuk korporasi", classification="FVOCI",
                         rating=h["rating"], face=h["mv"] / (1 + eps), md_base=rng.uniform(1.0, 3.5),
                         price_eps=eps, encumbered=False))
    h = pd.DataFrame(rows)
    years = h.md_base * rng.uniform(1.08, 1.25, len(h))
    h["maturity_date"] = [(REPORTING_DATE + pd.DateOffset(days=int(y * 365.25))).strftime("%Y-%m-%d") for y in years]
    return h, idx


def investment_portfolio(h: pd.DataFrame, idx: np.ndarray, targets: pd.DataFrame, capital: np.ndarray) -> pd.DataFrame:
    fv = (h.classification == "FVOCI").to_numpy()
    out = []
    for t, period in enumerate(MONTHLY_PERIODS):
        mv = h.face.to_numpy() * (1 + h.price_eps.to_numpy()) * idx[t]
        base = h.md_base.to_numpy()
        # MR02: Σ_FVOCI MV×MD = MR02 × modal ; IV04: Σ MV×MD / Σ MV
        f_fv = targets["MR02"].iloc[t] * capital[t] / np.sum(mv[fv] * base[fv])
        need_ac = targets["IV04"].iloc[t] * mv.sum() - targets["MR02"].iloc[t] * capital[t]
        f_ac = need_ac / np.sum(mv[~fv] * base[~fv])
        md = np.where(fv, base * f_fv, base * f_ac)
        out.append(pd.DataFrame(dict(
            period=period, holding_id=h.holding_id, issuer=h.issuer, issuer_type=h.issuer_type,
            instrument=h.instrument, classification=h.classification, rating=h.rating,
            face_value=h.face.round(6), market_value=np.round(mv, 6), modified_duration=np.round(md, 6),
            maturity_date=h.maturity_date, encumbered_flag=h.encumbered)))
    return pd.concat(out, ignore_index=True)


def carrying_by_period(h: pd.DataFrame, idx: np.ndarray) -> pd.DataFrame:
    """Nilai tercatat: FVOCI = market value, AC = face (proxy amortized cost, dibeli par)."""
    fv = (h.classification == "FVOCI").to_numpy()
    rows = []
    for t, period in enumerate(MONTHLY_PERIODS):
        mv = h.face.to_numpy() * (1 + h.price_eps.to_numpy()) * idx[t]
        carry = np.where(fv, mv, h.face.to_numpy())
        rows.append(dict(period=period, fvoci=carry[fv].sum(), ac=carry[~fv].sum(),
                         unencumbered=carry[~h.encumbered.to_numpy()].sum()))
    return pd.DataFrame(rows).set_index("period")
