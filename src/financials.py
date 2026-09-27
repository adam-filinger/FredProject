"""
financials.py - Download and store fundamental financial data via yfinance .info.

Public API
----------
update_all() -> None
save_snapshot(stock_id, ticker, date) -> bool
load_latest() -> pd.DataFrame   (pivoted: rows=metrics, cols=tickers)
load_history(ticker) -> pd.DataFrame
"""

import yfinance as yf
import pandas as pd
from datetime import date
import db


# Map: DB column name -> yfinance .info key
INFO_FIELD_MAP: dict[str, str] = {
    # Valuation
    "market_cap":                "marketCap",
    "enterprise_value":          "enterpriseValue",
    "trailing_pe":               "trailingPE",
    "forward_pe":                "forwardPE",
    "peg_ratio":                 "pegRatio",
    "price_to_book":             "priceToBook",
    "price_to_sales_ttm":        "priceToSalesTrailing12Months",
    "ev_to_revenue":             "enterpriseToRevenue",
    "ev_to_ebitda":              "enterpriseToEbitda",
    # Profitability
    "profit_margins":            "profitMargins",
    "gross_margins":             "grossMargins",
    "ebitda_margins":            "ebitdaMargins",
    "operating_margins":         "operatingMargins",
    "return_on_assets":          "returnOnAssets",
    "return_on_equity":          "returnOnEquity",
    # Growth
    "earnings_growth":           "earningsGrowth",
    "revenue_growth":            "revenueGrowth",
    "earnings_quarterly_growth": "earningsQuarterlyGrowth",
    # Income / Cash
    "total_revenue":             "totalRevenue",
    "gross_profits":             "grossProfits",
    "ebitda":                    "ebitda",
    "net_income":                "netIncomeToCommon",
    "free_cashflow":             "freeCashflow",
    "operating_cashflow":        "operatingCashflow",
    # Balance Sheet
    "total_cash":                "totalCash",
    "total_cash_per_share":      "totalCashPerShare",
    "total_debt":                "totalDebt",
    "debt_to_equity":            "debtToEquity",
    "quick_ratio":               "quickRatio",
    "current_ratio":             "currentRatio",
    # Per-Share
    "trailing_eps":              "trailingEps",
    "forward_eps":               "forwardEps",
    "book_value":                "bookValue",
    "revenue_per_share":         "revenuePerShare",
    # Dividends
    "dividend_rate":             "dividendRate",
    "dividend_yield":            "dividendYield",
    "payout_ratio":              "payoutRatio",
    "five_year_avg_div_yield":   "fiveYearAvgDividendYield",
    # Risk / Market
    "beta":                      "beta",
    "fifty_two_week_high":       "fiftyTwoWeekHigh",
    "fifty_two_week_low":        "fiftyTwoWeekLow",
    "shares_outstanding":        "sharesOutstanding",
    "float_shares":              "floatShares",
    "shares_short":              "sharesShort",
    "short_ratio":               "shortRatio",
    "short_percent_of_float":    "shortPercentOfFloat",
    # Analyst Targets
    "target_high_price":         "targetHighPrice",
    "target_low_price":          "targetLowPrice",
    "target_mean_price":         "targetMeanPrice",
    "target_median_price":       "targetMedianPrice",
    "recommendation_key":        "recommendationKey",
    "recommendation_mean":       "recommendationMean",
    "num_analyst_opinions":      "numberOfAnalystOpinions",
}

_DB_COLS = list(INFO_FIELD_MAP.keys())


def _fetch_info(ticker: str) -> dict | None:
    """
    Call yfinance and extract the mapped fields.
    Returns a dict keyed by DB column name, or None on failure.
    """
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        print(f"  {ticker}: could not fetch info -- {e}")
        return None

    if not info or info.get("quoteType") is None:
        print(f"  {ticker}: empty or invalid info response.")
        return None

    row: dict = {}
    for db_col, info_key in INFO_FIELD_MAP.items():
        val = info.get(info_key)
        if val is not None and not isinstance(val, str):
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = None
        row[db_col] = val
    return row


def save_snapshot(stock_id: int, ticker: str, snapshot_date: str) -> bool:
    """
    Fetch and store one daily fundamental snapshot.

    Incremental: skips if a row for (stock_id, snapshot_date) already exists.
    Returns True if a new row was inserted.
    """
    conn = db.get_conn()
    existing = conn.execute(
        "SELECT id FROM stock_financials WHERE stock_id = ? AND snapshot_date = ?",
        (stock_id, snapshot_date),
    ).fetchone()

    if existing:
        print(f"  {ticker}: snapshot for {snapshot_date} already exists -- skipping.")
        conn.close()
        return False

    row = _fetch_info(ticker)
    if row is None:
        conn.close()
        return False

    cols         = ["stock_id", "snapshot_date"] + _DB_COLS
    values       = [stock_id, snapshot_date] + [row[c] for c in _DB_COLS]
    placeholders = ", ".join(["?"] * len(cols))
    col_names    = ", ".join(cols)

    conn.execute(
        f"INSERT OR IGNORE INTO stock_financials ({col_names}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    conn.close()

    non_null = sum(1 for v in row.values() if v is not None)
    print(f"  {ticker}: saved snapshot for {snapshot_date} ({non_null}/{len(_DB_COLS)} fields).")
    return True


def update_all() -> None:
    """Download and store today's financial snapshot for every watchlist stock."""
    today = date.today().isoformat()
    conn  = db.get_conn()
    watchlist = pd.read_sql_query(
        "SELECT ID, ticker FROM stock ORDER BY ticker", conn
    )
    conn.close()

    if watchlist.empty:
        print("Watchlist is empty. Add stocks with watchlist.add() first.")
        return

    print(f"Fetching financials for {len(watchlist)} stock(s) -- snapshot: {today}\n")
    saved = 0
    for _, s in watchlist.iterrows():
        if save_snapshot(s["ID"], s["ticker"], today):
            saved += 1
    print(f"\nDone. {saved} new snapshot(s) saved.")


def load_latest() -> pd.DataFrame:
    """
    Return the most recent snapshot for every watchlist stock.

    Pivoted so rows = metric names, columns = ticker symbols.
    """
    conn = db.get_conn()
    df = pd.read_sql_query(
        """
        SELECT s.ticker, f.*
        FROM   stock_financials f
        JOIN   stock            s ON s.ID = f.stock_id
        WHERE  f.snapshot_date = (
            SELECT MAX(f2.snapshot_date)
            FROM   stock_financials f2
            WHERE  f2.stock_id = f.stock_id
        )
        ORDER  BY s.ticker
        """,
        conn,
    )
    conn.close()

    if df.empty:
        return df

    drop = [c for c in ("id", "stock_id", "snapshot_date") if c in df.columns]
    return df.drop(columns=drop).set_index("ticker").T


def load_history(ticker: str) -> pd.DataFrame:
    """
    Return all stored snapshots for a single ticker, indexed by snapshot_date.
    """
    ticker = ticker.upper().strip()
    conn = db.get_conn()
    df = pd.read_sql_query(
        """
        SELECT f.*
        FROM   stock_financials f
        JOIN   stock            s ON s.ID = f.stock_id
        WHERE  s.ticker = ?
        ORDER  BY f.snapshot_date ASC
        """,
        conn,
        params=(ticker,),
    )
    conn.close()
    return df.set_index("snapshot_date") if not df.empty else df
