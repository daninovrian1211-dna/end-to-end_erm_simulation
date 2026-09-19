"""Generator data sintetis ASB (spec §8.2). Seed 42, deterministik.

Pemakaian: `python -m erm.generator [--out data/raw] [--seed 42]` atau `generate_all()`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import (balance_sheet, calibrate, compliance, credit, investment, legal, liquidity, market,
               operational, rate_of_return, reputation, strategic)

STREAMS = ["targets", "investment", "core", "credit", "deposits", "top_depositors", "maturity", "market",
           "rate_of_return", "operational", "compliance", "legal", "complaints", "sentiment"]
OUTPUT_FILES = ["balance_sheet_monthly", "capital_monthly", "financing_portfolio", "deposits_monthly",
                "top_depositors", "maturity_profile", "market_positions", "investment_portfolio",
                "rate_of_return_monthly", "operational_events", "compliance_events", "legal_cases",
                "complaints", "sentiment_monthly", "strategic_monthly"]


def generate(seed: int | None = None) -> dict[str, pd.DataFrame]:
    profile = calibrate.load_yaml("bank_profile.yaml")
    seed = profile["reporting"]["random_seed"] if seed is None else seed
    rngs = dict(zip(STREAMS, (np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(len(STREAMS)))))

    targets = calibrate.kri_targets(rngs["targets"])
    holdings, idx = investment.build_holdings(targets, profile, rngs["investment"])
    carry = investment.carrying_by_period(holdings, idx)
    core = balance_sheet.build_core(profile, targets, carry, rngs["core"])
    deposits = liquidity.deposits_monthly(core, targets, profile, rngs["deposits"])
    return {
        "balance_sheet_monthly": balance_sheet.balance_sheet_monthly(core),
        "capital_monthly": balance_sheet.capital_monthly(core),
        "financing_portfolio": credit.financing_portfolio(targets, core, rngs["credit"]),
        "deposits_monthly": deposits,
        "top_depositors": liquidity.top_depositors(core, targets, rngs["top_depositors"]),
        "maturity_profile": liquidity.maturity_profile(core, targets, rngs["maturity"]),
        "market_positions": market.market_positions(core, targets, rngs["market"]),
        "investment_portfolio": investment.investment_portfolio(holdings, idx, targets, core.equity.to_numpy()),
        "rate_of_return_monthly": rate_of_return.rate_of_return_monthly(deposits, targets, rngs["rate_of_return"]),
        "operational_events": operational.operational_events(targets, core, rngs["operational"]),
        "compliance_events": compliance.compliance_events(targets, rngs["compliance"]),
        "legal_cases": legal.legal_cases(targets, core, rngs["legal"]),
        "complaints": reputation.complaints(targets, rngs["complaints"]),
        "sentiment_monthly": reputation.sentiment_monthly(targets, rngs["sentiment"]),
        "strategic_monthly": strategic.strategic_monthly(targets, profile),
    }


def write(data: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in OUTPUT_FILES:
        path = out_dir / f"{name}.csv"
        data[name].to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
        paths.append(path)
    return paths


def generate_all(out_dir: Path | str = calibrate.RAW_DIR, seed: int | None = None) -> list[Path]:
    return write(generate(seed), Path(out_dir))
