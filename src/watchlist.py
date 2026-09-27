"""
watchlist.py - Manage the stock watchlist in the MacroScope DB.

Public API
----------
add(ticker, name=None, currency='USD') -> None
remove(ticker) -> None
get_all() -> pd.DataFrame
"""

import yfinance as yf
import pandas as pd
import db


def add(ticker: str, name: str | None = None, currency: str = "USD") -> None:
    """
    Add a stock to the watchlist.

    If the ticker is already present, does nothing.
    Name and currency are auto-fetched from yfinance when not provided.
    """
    ticker = ticker.upper().strip()
    conn = db.get_conn()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT ID FROM stock WHERE ticker = ?", (ticker,)
    ).fetchone()

    if existing:
        print(f"  {ticker} is already in the watchlist (ID={existing[0]}).")
        conn.close()
        return

    if name is None:
        try:
            info = yf.Ticker(ticker).info
            name = info.get("longName") or info.get("shortName") or ticker
            currency = info.get("currency", currency)
        except Exception:
            name = ticker

    cur.execute(
        "INSERT INTO stock (name, currency, ticker) VALUES (?, ?, ?)",
        (name, currency, ticker),
    )
    conn.commit()
    conn.close()
    print(f"  Added {ticker} ({name}) to watchlist.")


def remove(ticker: str) -> None:
    """
    Remove a stock and all its related price and financial data from the DB.
    """
    ticker = ticker.upper().strip()
    conn = db.get_conn()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT ID FROM stock WHERE ticker = ?", (ticker,)
    ).fetchone()

    if not row:
        print(f"  {ticker} not found in watchlist.")
        conn.close()
        return

    stock_id = row[0]
    cur.execute("DELETE FROM price_data        WHERE stock_id = ?", (stock_id,))
    cur.execute("DELETE FROM stock_financials  WHERE stock_id = ?", (stock_id,))
    cur.execute("DELETE FROM stock             WHERE ID = ?",       (stock_id,))
    conn.commit()
    conn.close()
    print(f"  Removed {ticker} and all its data.")


def get_all() -> pd.DataFrame:
    """
    Return the full watchlist as a DataFrame.

    Columns: ID, ticker, name, currency, last_updated
    """
    conn = db.get_conn()
    df = pd.read_sql_query(
        "SELECT ID, ticker, name, currency, last_updated FROM stock ORDER BY ticker",
        conn,
    )
    conn.close()
    return df
