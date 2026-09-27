"""
price_data.py - Download and store hourly close prices via yfinance.

Public API
----------
update_all() -> None
download_and_save(ticker, stock_id) -> int   (rows inserted)
load(ticker) -> pd.DataFrame                 (index=datetime UTC, col='close')
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
import db


INTERVAL       = "1h"    # Hourly candles
FALLBACK_PERIOD = "730d"  # Used when no prior data exists


def _get_last_stored_time(stock_id: int) -> str | None:
    """Return the ISO timestamp of the most recent stored candle, or None."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT MAX(time) FROM price_data WHERE stock_id = ?", (stock_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def download_and_save(ticker: str, stock_id: int) -> int:
    """
    Incrementally download hourly close prices for a single stock.

    Strategy:
    - If no data exists: full download (FALLBACK_PERIOD).
    - If data exists:    fetch from the last stored date onwards (overlap safe).

    Prices are stored as integer cents to avoid floating-point drift.

    Returns the number of new rows inserted.
    """
    last_time = _get_last_stored_time(stock_id)

    if last_time:
        start_ts = pd.Timestamp(last_time)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize("UTC")
        start_str = start_ts.strftime("%Y-%m-%d")
        print(f"  {ticker}: incremental fetch from {start_str}")
        hist = yf.Ticker(ticker).history(start=start_str, interval=INTERVAL)
    else:
        print(f"  {ticker}: full fetch ({FALLBACK_PERIOD})")
        hist = yf.Ticker(ticker).history(period=FALLBACK_PERIOD, interval=INTERVAL)

    if hist.empty:
        print(f"  {ticker}: no data returned.")
        return 0

    # Normalise index to UTC-aware ISO strings
    hist.index = pd.DatetimeIndex(hist.index).tz_convert("UTC")

    rows = []
    for ts, row in hist.iterrows():
        ts_str = ts.isoformat()
        if last_time and ts_str <= last_time:
            continue                          # skip overlap
        close = row.get("Close")
        if close is None or pd.isna(close):
            continue
        rows.append((stock_id, ts_str, int(round(close * 100))))

    if not rows:
        print(f"  {ticker}: already up-to-date.")
        return 0

    conn = db.get_conn()
    conn.executemany(
        "INSERT OR IGNORE INTO price_data (stock_id, time, price) VALUES (?, ?, ?)",
        rows,
    )
    conn.execute(
        "UPDATE stock SET last_updated = ? WHERE ID = ?",
        (datetime.now(timezone.utc).isoformat(), stock_id),
    )
    conn.commit()
    conn.close()
    print(f"  {ticker}: saved {len(rows)} new rows.")
    return len(rows)


def update_all() -> None:
    """Download and save hourly prices for every stock in the watchlist."""
    conn = db.get_conn()
    watchlist = pd.read_sql_query(
        "SELECT ID, ticker FROM stock ORDER BY ticker", conn
    )
    conn.close()

    if watchlist.empty:
        print("Watchlist is empty. Add stocks with watchlist.add() first.")
        return

    print(f"Updating prices for {len(watchlist)} stock(s)...\n")
    total = 0
    for _, s in watchlist.iterrows():
        total += download_and_save(s["ticker"], s["ID"])
    print(f"\nDone. {total} new rows inserted.")


def load(ticker: str) -> pd.DataFrame:
    """
    Load stored hourly close prices for a ticker from the DB.

    Returns a DataFrame with:
    - index: 'datetime' (UTC-aware pd.DatetimeTZDtype)
    - column: 'close' (float, real price in original currency)
    """
    ticker = ticker.upper().strip()
    conn = db.get_conn()
    df = pd.read_sql_query(
        """
        SELECT pd.time, pd.price
        FROM   price_data pd
        JOIN   stock      s  ON s.ID = pd.stock_id
        WHERE  s.ticker = ?
        ORDER  BY pd.time ASC
        """,
        conn,
        params=(ticker,),
    )
    conn.close()

    if df.empty:
        return df

    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    df["close"] = df["price"] / 100.0
    return df.drop(columns=["price"])
