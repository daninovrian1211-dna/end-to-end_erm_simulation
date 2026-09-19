"""Portofolio pembiayaan per obligor → financing_portfolio.csv.

1) Master obligor realistis: segmen, sektor, akad, margin, tenor, ukuran (lognormal), latent risk.
2) Per bulan: NPF dan Kol-2 dipilih berurutan dari latent risk (migrasi Kol-2 → NPF, NPF bertahap naik).
3) calibrate.rake menyesuaikan outstanding agar total, NPF, NPF UMKM, Kol-2, top-10, sektor terbesar,
   dan porsi margin tetap tenor >3 tahun tepat pada jalur target."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibrate import LOOKBACK, MONTHLY_PERIODS, rake

LARGEST_SECTOR = "Pertanian & perkebunan"
SECTORS = {  # probabilitas awal (sebelum kalibrasi)
    "Pertanian & perkebunan": 0.20, "Perdagangan besar & eceran": 0.18, "Industri pengolahan": 0.15,
    "Konstruksi": 0.11, "Transportasi & pergudangan": 0.09, "Real estate & jasa usaha": 0.10,
    "Pertambangan & energi": 0.06, "Jasa pendidikan & kesehatan": 0.06, "Akomodasi & makan minum": 0.05,
}
AKAD = {"UMKM": {"murabahah": 0.60, "musyarakah": 0.22, "ijarah": 0.12, "mudharabah": 0.06},
        "Korporasi": {"murabahah": 0.32, "musyarakah": 0.40, "ijarah": 0.18, "mudharabah": 0.10}}
KOL2_UMKM_MULT = 1.6  # rasio Kol-2 UMKM = 1,6 × rasio Kol-2 total
N_UMKM, N_CORP, N_TOP = 5500, 500, 10


def build_obligors(rng: np.random.Generator) -> pd.DataFrame:
    n = N_UMKM + N_CORP
    seg = np.array(["UMKM"] * N_UMKM + ["Korporasi"] * N_CORP)
    top = np.zeros(n, bool)
    top[N_UMKM:N_UMKM + N_TOP] = True
    size = np.where(seg == "UMKM", rng.lognormal(np.log(1.8), 0.8, n), np.minimum(rng.lognormal(np.log(35), 0.9, n), 250))
    size[top] = rng.uniform(550, 950, N_TOP)
    sec_names, sec_p = list(SECTORS), np.array(list(SECTORS.values()))
    sector = rng.choice(sec_names, n, p=sec_p)
    non_largest = [s for s in sec_names if s != LARGEST_SECTOR and s not in ("Akomodasi & makan minum",)]
    sector[top] = rng.choice(non_largest, N_TOP)
    akad = np.empty(n, dtype=object)
    for s in ("UMKM", "Korporasi"):
        m = seg == s
        akad[m] = rng.choice(list(AKAD[s]), m.sum(), p=list(AKAD[s].values()))
    fixed = (akad == "murabahah") | ((akad == "ijarah") & (rng.random(n) < 0.7))
    margin = np.where(fixed, "fixed", "floating")
    tenor_sep = np.where(seg == "UMKM", rng.integers(3, 61, n), rng.integers(6, 109, n))
    long_boost = fixed & (rng.random(n) < 0.45)
    tenor_sep = np.where(long_boost, tenor_sep + rng.integers(24, 48, n), tenor_sep)
    # originasi: 88% sebelum Jul-2025, sisanya tersebar pada 15 bulan periode data
    new = (rng.random(n) < 0.12) & ~top
    orig_idx = np.where(new, rng.integers(0, len(MONTHLY_PERIODS), n), -1)
    old_periods = pd.period_range("2019-01", "2025-06", freq="M").strftime("%Y-%m").to_numpy()
    orig_period = np.where(new, np.array(MONTHLY_PERIODS)[np.clip(orig_idx, 0, None)], rng.choice(old_periods, n))
    ids = [f"OBL-{i+1:05d}" for i in range(n)]
    return pd.DataFrame(dict(obligor_id=ids, segment=seg, top10=top, size=size, sector=sector, akad=akad,
                             margin_type=margin, tenor_sep=tenor_sep, orig_idx=orig_idx,
                             origination_period=orig_period, risk=rng.random(n)))


def financing_portfolio(targets: pd.DataFrame, core: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ob = build_obligors(rng)
    n = len(ob)
    size = ob["size"].to_numpy()
    risk = ob["risk"].to_numpy()
    seg_u = (ob.segment == "UMKM").to_numpy()
    top = ob.top10.to_numpy()
    seasoned = (ob.orig_idx < 0).to_numpy()
    in_largest = (ob.sector == LARGEST_SECTOR).to_numpy()
    first_npf = np.full(n, 10**6)
    dpd_seed = rng.random(n)
    out = []
    for t, period in enumerate(MONTHLY_PERIODS):
        active = (ob.orig_idx <= t).to_numpy()
        rem = ob.tenor_sep.to_numpy() + (len(MONTHLY_PERIODS) - 1 - t)
        F = core.gross_financing.iloc[t]
        cr01, cr02, cr03 = (targets[k].iloc[t] / 100 for k in ("CR01", "CR02", "CR03"))
        u_tot, c_tot = 0.30 * F, 0.70 * F
        u_npf = cr02 * u_tot
        c_npf = cr01 * F - u_npf
        u_k2 = min(KOL2_UMKM_MULT * cr03, 0.5) * u_tot
        c_k2 = cr03 * F - u_k2

        status = np.zeros(n, int)  # 0 lancar, 1 kol2, 2 npf
        for segmask, npf_amt, k2_amt in ((seg_u, u_npf, u_k2), (~seg_u, c_npf, c_k2)):
            base_tot = size[active & segmask].sum()
            cand = np.where(active & segmask & ~top & seasoned)[0]
            cand = cand[np.argsort(risk[cand])]
            share_npf = npf_amt / (u_tot if segmask is seg_u else c_tot)
            share_k2 = k2_amt / (u_tot if segmask is seg_u else c_tot)
            cum = np.cumsum(size[cand]) / base_tot
            k_npf = int(np.searchsorted(cum, share_npf)) + 1
            status[cand[:k_npf]] = 2
            cand2 = np.where(active & segmask & ~top & (status == 0) & ((ob.orig_idx <= t - 3) | seasoned).to_numpy())[0]
            cand2 = cand2[np.argsort(risk[cand2])]
            cum2 = np.cumsum(size[cand2]) / base_tot
            k_k2 = int(np.searchsorted(cum2, share_k2)) + 1
            status[cand2[:k_k2]] = 1
        newly = (status == 2) & (first_npf > 10**5)
        first_npf[newly] = -rng.integers(0, 18, newly.sum()) if t == 0 else t
        first_npf[status != 2] = 10**6

        idx = np.where(active)[0]
        cell = np.where(seg_u, status, np.where(top, 5, np.array([6, 4, 3])[status]))
        # kode sel: 0 U-lancar,1 U-kol2,2 U-npf,3 C-npf,4 C-kol2,5 C-top10,6 C-lancar
        cell_t = np.array([u_tot - u_npf - u_k2, u_k2, u_npf, c_npf, c_k2,
                           targets["CR04"].iloc[t] / 100 * F, 0.0])
        cell_t[6] = c_tot - c_npf - c_k2 - cell_t[5]
        sec_t = np.array([targets["CR05"].iloc[t] / 100 * F, 0.0]); sec_t[1] = F - sec_t[0]
        fl = (ob.margin_type.to_numpy() == "fixed") & (rem > 36)
        fl_t = np.array([targets["RR04"].iloc[t] / 100 * F, 0.0]); fl_t[1] = F - fl_t[0]
        w = rake(size[idx], [(cell[idx], cell_t), ((~in_largest[idx]).astype(int), sec_t),
                             ((~fl[idx]).astype(int), fl_t)])

        st = status[idx]
        months_npf = t - first_npf[idx]
        coll = np.select([st == 0, st == 1, months_npf < 3, months_npf < 6], [1, 2, 3, 4], 5)
        u = dpd_seed[idx]
        dpd = np.select([coll == 1, coll == 2, coll == 3, coll == 4],
                        [0, 1 + (u * 89).astype(int), 91 + (u * 29).astype(int), 121 + (u * 59).astype(int)],
                        181 + (np.clip(months_npf, 6, None) - 6) * 30 + (u * 29).astype(int))
        o = ob.iloc[idx]
        out.append(pd.DataFrame(dict(
            period=period, obligor_id=o.obligor_id.to_numpy(), segment=o.segment.to_numpy(),
            sector=o.sector.to_numpy(), akad=o.akad.to_numpy(), outstanding=np.round(w, 6),
            collectibility=coll, dpd=dpd, margin_type=o.margin_type.to_numpy(),
            remaining_tenor_months=rem[idx], origination_period=o.origination_period.to_numpy())))
    return pd.concat(out, ignore_index=True)
