"""Reference universe: benchmarks, sector ETFs and a curated set of US equities.

Used to seed the `stocks` table (search works offline) and as the world the
mock provider simulates. Sector context uses SPDR sector ETFs as sector
benchmarks and SPY as the market benchmark, for every provider.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    sector: str | None
    benchmark: str | None  # sector ETF symbol
    price: float  # "normal" reference price used by the mock world
    avg_volume: float
    daily_vol_pct: float
    kind: str = "EQUITY"


MARKET_BENCHMARK = "SPY"

SECTORS: dict[str, str] = {
    "XLK": "Technology",
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLE": "Energy",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
}
SECTOR_TO_ETF = {v: k for k, v in SECTORS.items()}

_ETF_PRICES = {
    "XLK": (285.40, 9.1e6, 1.3), "XLC": (112.30, 5.2e6, 1.2), "XLY": (236.10, 4.1e6, 1.3),
    "XLF": (53.40, 38e6, 1.1), "XLV": (141.20, 8.3e6, 0.9), "XLE": (88.70, 15e6, 1.4),
    "XLP": (79.80, 10e6, 0.7), "XLI": (152.60, 9.4e6, 1.0), "XLU": (84.10, 11e6, 1.0),
    "XLRE": (42.30, 6.5e6, 1.2), "XLB": (89.50, 6.1e6, 1.1),
}

_EQUITIES: list[tuple[str, str, str, str, float, float, float]] = [
    # symbol, name, exchange, sector ETF, price, avg volume, daily vol %
    ("NVDA", "NVIDIA Corporation", "NASDAQ", "XLK", 180.20, 185e6, 2.4),
    ("AAPL", "Apple Inc.", "NASDAQ", "XLK", 232.40, 52e6, 1.5),
    ("MSFT", "Microsoft Corporation", "NASDAQ", "XLK", 512.30, 21e6, 1.3),
    ("AMD", "Advanced Micro Devices, Inc.", "NASDAQ", "XLK", 162.75, 45e6, 3.0),
    ("AVGO", "Broadcom Inc.", "NASDAQ", "XLK", 338.10, 24e6, 2.5),
    ("ORCL", "Oracle Corporation", "NYSE", "XLK", 214.60, 12e6, 2.2),
    ("CRM", "Salesforce, Inc.", "NYSE", "XLK", 268.40, 7.1e6, 2.0),
    ("ADBE", "Adobe Inc.", "NASDAQ", "XLK", 372.80, 3.4e6, 2.0),
    ("INTC", "Intel Corporation", "NASDAQ", "XLK", 31.20, 88e6, 2.8),
    ("GOOGL", "Alphabet Inc.", "NASDAQ", "XLC", 246.50, 31e6, 1.7),
    ("META", "Meta Platforms, Inc.", "NASDAQ", "XLC", 712.30, 12e6, 2.1),
    ("NFLX", "Netflix, Inc.", "NASDAQ", "XLC", 1190.40, 3.9e6, 2.0),
    ("DIS", "The Walt Disney Company", "NYSE", "XLC", 112.60, 9.2e6, 1.5),
    ("AMZN", "Amazon.com, Inc.", "NASDAQ", "XLY", 228.90, 41e6, 1.9),
    ("TSLA", "Tesla, Inc.", "NASDAQ", "XLY", 418.30, 98e6, 3.5),
    ("NKE", "NIKE, Inc.", "NYSE", "XLY", 72.40, 11e6, 2.0),
    ("HD", "The Home Depot, Inc.", "NYSE", "XLY", 391.20, 3.6e6, 1.3),
    ("MCD", "McDonald's Corporation", "NYSE", "XLY", 301.50, 3.2e6, 1.0),
    ("JPM", "JPMorgan Chase & Co.", "NYSE", "XLF", 298.70, 9.4e6, 1.3),
    ("BAC", "Bank of America Corporation", "NYSE", "XLF", 49.80, 38e6, 1.6),
    ("GS", "The Goldman Sachs Group, Inc.", "NYSE", "XLF", 742.10, 2.3e6, 1.7),
    ("V", "Visa Inc.", "NYSE", "XLF", 348.20, 6.8e6, 1.1),
    ("MA", "Mastercard Incorporated", "NYSE", "XLF", 573.40, 2.9e6, 1.2),
    ("JNJ", "Johnson & Johnson", "NYSE", "XLV", 178.30, 7.6e6, 0.9),
    ("UNH", "UnitedHealth Group Incorporated", "NYSE", "XLV", 342.10, 8.9e6, 1.8),
    ("PFE", "Pfizer Inc.", "NYSE", "XLV", 25.10, 41e6, 1.5),
    ("LLY", "Eli Lilly and Company", "NYSE", "XLV", 812.40, 3.8e6, 2.0),
    ("MRK", "Merck & Co., Inc.", "NYSE", "XLV", 86.70, 12e6, 1.3),
    ("XOM", "Exxon Mobil Corporation", "NYSE", "XLE", 116.20, 15e6, 1.4),
    ("CVX", "Chevron Corporation", "NYSE", "XLE", 152.30, 8.1e6, 1.4),
    ("COP", "ConocoPhillips", "NYSE", "XLE", 94.60, 7.2e6, 1.8),
    ("KO", "The Coca-Cola Company", "NYSE", "XLP", 69.40, 14e6, 0.8),
    ("PEP", "PepsiCo, Inc.", "NASDAQ", "XLP", 146.20, 6.9e6, 1.0),
    ("WMT", "Walmart Inc.", "NASDAQ", "XLP", 101.30, 17e6, 1.1),
    ("PG", "The Procter & Gamble Company", "NYSE", "XLP", 158.70, 6.7e6, 0.9),
    ("COST", "Costco Wholesale Corporation", "NASDAQ", "XLP", 942.10, 2.1e6, 1.2),
    ("BA", "The Boeing Company", "NYSE", "XLI", 216.40, 8.8e6, 2.2),
    ("CAT", "Caterpillar Inc.", "NYSE", "XLI", 471.20, 2.9e6, 1.7),
    ("GE", "GE Aerospace", "NYSE", "XLI", 284.60, 5.4e6, 1.8),
    ("UPS", "United Parcel Service, Inc.", "NYSE", "XLI", 98.30, 6.2e6, 1.6),
    ("NEE", "NextEra Energy, Inc.", "NYSE", "XLU", 74.50, 9.9e6, 1.5),
    ("DUK", "Duke Energy Corporation", "NYSE", "XLU", 121.80, 3.3e6, 1.0),
    ("PLD", "Prologis, Inc.", "NYSE", "XLRE", 112.40, 4.1e6, 1.6),
    ("AMT", "American Tower Corporation", "NYSE", "XLRE", 205.30, 2.6e6, 1.5),
    ("LIN", "Linde plc", "NASDAQ", "XLB", 462.10, 2.2e6, 1.1),
]


def _build() -> dict[str, Instrument]:
    out: dict[str, Instrument] = {
        MARKET_BENCHMARK: Instrument(MARKET_BENCHMARK, "SPDR S&P 500 ETF Trust", "NYSE Arca", None, None, 668.20, 62e6, 0.9, "INDEX_ETF")
    }
    for etf, (price, vol, dv) in _ETF_PRICES.items():
        out[etf] = Instrument(etf, f"{SECTORS[etf]} Select Sector SPDR Fund", "NYSE Arca", SECTORS[etf], None, price, vol, dv, "SECTOR_ETF")
    for sym, name, exch, etf, price, vol, dv in _EQUITIES:
        out[sym] = Instrument(sym, name, exch, SECTORS[etf], etf, price, vol, dv)
    return out


UNIVERSE: dict[str, Instrument] = _build()
BENCHMARK_SYMBOLS: list[str] = [MARKET_BENCHMARK, *SECTORS.keys()]

# Finnhub `finnhubIndustry` -> GICS-style sector used for sector context.
INDUSTRY_TO_SECTOR: dict[str, str] = {
    "Technology": "Technology", "Semiconductors": "Technology", "Software": "Technology",
    "Communications": "Communication Services", "Media": "Communication Services",
    "Telecommunication": "Communication Services", "Entertainment": "Communication Services",
    "Retail": "Consumer Discretionary", "Automobiles": "Consumer Discretionary",
    "Hotels, Restaurants & Leisure": "Consumer Discretionary", "Textiles, Apparel & Luxury Goods": "Consumer Discretionary",
    "Consumer products": "Consumer Staples", "Food Products": "Consumer Staples", "Beverages": "Consumer Staples",
    "Tobacco": "Consumer Staples",
    "Banking": "Financials", "Financial Services": "Financials", "Insurance": "Financials",
    "Pharmaceuticals": "Health Care", "Biotechnology": "Health Care", "Health Care": "Health Care",
    "Life Sciences Tools & Services": "Health Care", "Medical Devices": "Health Care",
    "Energy": "Energy", "Oil & Gas": "Energy",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Chemicals": "Materials", "Metals & Mining": "Materials", "Materials": "Materials", "Packaging": "Materials",
    "Aerospace & Defense": "Industrials", "Machinery": "Industrials", "Airlines": "Industrials",
    "Logistics & Transportation": "Industrials", "Industrial Conglomerates": "Industrials", "Construction": "Industrials",
}


def sector_for_industry(industry: str | None) -> tuple[str | None, str | None]:
    if not industry:
        return None, None
    sector = INDUSTRY_TO_SECTOR.get(industry)
    return sector, SECTOR_TO_ETF.get(sector) if sector else None
