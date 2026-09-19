"""Validasi dan rekonsiliasi data (spec §12 no. 1, 2, 7)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

ASSET_LINES = ["kas_giro_bi_gwm_wajib", "kas_giro_bi_excess", "penempatan_bank_lain", "sukuk_fvoci",
               "sukuk_amortized_cost", "pembiayaan_bruto", "cadangan_kerugian", "aset_lain"]
DPK_LINES = ["giro_wadiah", "tabungan", "deposito_mudharabah"]
ABS_TOL = 1e-3  # Rp miliar (akibat pembulatan 6 desimal per baris granular)


def _pivot(bs: pd.DataFrame) -> pd.DataFrame:
    return bs.pivot(index="period", columns="line_item", values="amount")


# ---------- §12 no. 1 ----------
def balance_check(bs: pd.DataFrame) -> pd.DataFrame:
    """Total aset vs liabilitas + ekuitas per bulan."""
    g = bs.groupby(["period", "category"]).amount.sum().unstack(fill_value=0.0)
    out = pd.DataFrame({"total_assets": g["asset"], "total_liab_equity": g["liability"] + g["equity"]})
    out["difference"] = out.total_assets - out.total_liab_equity
    return out


def anchor_expected(profile: dict) -> dict[str, float]:
    a = profile["balance_sheet_2026_09"]["assets"]
    le = profile["balance_sheet_2026_09"]["liabilities_equity"]
    return {
        "Kas & giro BI": a["cash_and_bi_current_account"], "Penempatan pada bank lain": a["placements_with_other_banks"],
        "Portofolio sukuk": a["sukuk_portfolio"], "Pembiayaan bruto": a["gross_financing"],
        "Cadangan kerugian": a["allowance_for_losses"], "Aset lain": a["other_assets"], "Total aset": a["total_assets"],
        "Giro wadiah": le["giro_wadiah"], "Tabungan": le["tabungan"], "Deposito mudharabah": le["deposito_mudharabah"],
        "Total DPK": le["total_dpk"], "Pendanaan lain": le["other_funding"], "Liabilitas lain": le["other_liabilities"],
        "Ekuitas": le["equity"], "Total liabilitas & ekuitas": le["total_liabilities_equity"],
        "Modal KPMM": profile["capital"]["capital_kpmm"], "ATMR": profile["capital"]["atmr"],
    }


def anchor_check(bs: pd.DataFrame, capital: pd.DataFrame, profile: dict) -> pd.DataFrame:
    """Nilai reporting date vs neraca jangkar §2 (toleransi ±0,5%)."""
    period = profile["reporting"]["period_end"]
    tol = profile["reporting"]["reconciliation_tolerance"]
    b = _pivot(bs).loc[period]
    cap = capital.set_index("period").loc[period]
    actual = {
        "Kas & giro BI": b.kas_giro_bi_gwm_wajib + b.kas_giro_bi_excess, "Penempatan pada bank lain": b.penempatan_bank_lain,
        "Portofolio sukuk": b.sukuk_fvoci + b.sukuk_amortized_cost, "Pembiayaan bruto": b.pembiayaan_bruto,
        "Cadangan kerugian": b.cadangan_kerugian, "Aset lain": b.aset_lain, "Total aset": b[ASSET_LINES].sum(),
        "Giro wadiah": b.giro_wadiah, "Tabungan": b.tabungan, "Deposito mudharabah": b.deposito_mudharabah,
        "Total DPK": b[DPK_LINES].sum(), "Pendanaan lain": b.pendanaan_lain, "Liabilitas lain": b.liabilitas_lain,
        "Ekuitas": b.ekuitas,
        "Total liabilitas & ekuitas": b[DPK_LINES + ["pendanaan_lain", "liabilitas_lain", "ekuitas"]].sum(),
        "Modal KPMM": cap.capital_kpmm, "ATMR": cap.atmr,
    }
    rows = []
    for item, exp in anchor_expected(profile).items():
        act = float(actual[item])
        dev = (act - exp) / abs(exp)
        rows.append(dict(item=item, spec=exp, generated=act, deviation_pct=dev * 100, within_tolerance=abs(dev) <= tol))
    return pd.DataFrame(rows)


# ---------- §12 no. 2 ----------
def granular_reconciliation(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Neraca vs agregasi granular per bulan: pembiayaan, sukuk, DPK (+ kontrol tambahan)."""
    b = _pivot(raw["balance_sheet_monthly"])
    fin = raw["financing_portfolio"].groupby("period").outstanding.sum()
    inv = raw["investment_portfolio"]
    carrying = np.where(inv.classification == "FVOCI", inv.market_value, inv.face_value)
    sukuk = pd.Series(carrying, index=inv.index).groupby(inv.period).sum()
    dep = raw["deposits_monthly"].groupby("period").balance.sum()
    mat = raw["maturity_profile"].groupby("period")[["assets_maturing", "liabilities_maturing"]].sum()
    rows = []
    checks = [
        ("Pembiayaan bruto", b.pembiayaan_bruto, fin, "financing_portfolio.outstanding"),
        ("Portofolio sukuk", b.sukuk_fvoci + b.sukuk_amortized_cost, sukuk, "investment_portfolio (FVOCI MV + AC face)"),
        ("Total DPK", b[DPK_LINES].sum(axis=1), dep, "deposits_monthly.balance"),
        ("Total aset", b[ASSET_LINES].sum(axis=1), mat.assets_maturing, "maturity_profile.assets_maturing"),
        ("Total liabilitas", b[DPK_LINES + ["pendanaan_lain", "liabilitas_lain"]].sum(axis=1), mat.liabilities_maturing,
         "maturity_profile.liabilities_maturing"),
    ]
    for item, ledger, granular, source in checks:
        for p in ledger.index:
            g = float(granular.get(p, np.nan))
            rows.append(dict(period=p, item=item, balance_sheet=float(ledger[p]), granular=g, source=source,
                             difference=g - float(ledger[p])))
    out = pd.DataFrame(rows)
    out["reconciled"] = out.difference.abs() <= ABS_TOL
    return out


def top_depositor_check(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Saldo 20 deposan terbesar per produk tidak boleh melebihi saldo produk."""
    td = raw["top_depositors"].groupby(["period", "product"]).balance.sum()
    dep = raw["deposits_monthly"].set_index(["period", "product"]).balance
    df = pd.DataFrame({"top20": td}).join(dep.rename("product_balance"))
    df["ok"] = df.top20 <= df.product_balance
    return df


def reconciliation_table(raw: dict[str, pd.DataFrame], period: str) -> pd.DataFrame:
    g = granular_reconciliation(raw)
    return g[g.period == period].drop(columns="period").reset_index(drop=True)


# ---------- §12 no. 7 ----------
def file_hashes(directory: Path | str, pattern: str = "*.csv") -> dict[str, str]:
    directory = Path(directory)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.glob(pattern))}
