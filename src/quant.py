"""
quant.py - Technical indicators and BUY/HOLD/SELL signal generation.

Algorithm: EMA Crossover (20 vs 50 periods) + RSI(14) filter
  BUY  -- EMA20 > EMA50  AND  40 < RSI < 70  (uptrend, not overbought)
  SELL -- EMA20 < EMA50  AND  RSI < 45       (downtrend, momentum confirms)
  HOLD -- everything else

Public API
----------
compute_ema(series, span) -> pd.Series
compute_rsi(series, period=14) -> pd.Series
generate_signal(close) -> dict
analyse_watchlist() -> pd.DataFrame
"""

import numpy as np
import pandas as pd
import db
import price_data as pd_module


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's RSI using exponential smoothing (alpha = 1/period).
    Returns values in [0, 100].
    """
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def generate_signal(
    close: pd.Series,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
) -> dict:
    """
    Compute the EMA crossover + RSI signal on a Close price series.

    Returns a dict with keys:
      signal       -- 'BUY' | 'HOLD' | 'SELL' | 'INSUFFICIENT DATA'
      last_close   -- most recent closing price
      ema_fast     -- latest fast EMA value
      ema_slow     -- latest slow EMA value
      rsi          -- latest RSI value
      trend        -- 'UP' | 'DOWN'
    """
    _empty = dict(
        signal="INSUFFICIENT DATA",
        last_close=None, ema_fast=None, ema_slow=None,
        rsi=None, trend=None,
    )

    if len(close) < ema_slow + rsi_period:
        return _empty

    fast = compute_ema(close, ema_fast)
    slow = compute_ema(close, ema_slow)
    rsi  = compute_rsi(close, rsi_period)

    last_close = close.iloc[-1]
    last_fast  = fast.iloc[-1]
    last_slow  = slow.iloc[-1]
    last_rsi   = rsi.iloc[-1]
    trend      = "UP" if last_fast > last_slow else "DOWN"

    if trend == "UP" and 40 < last_rsi < 70:
        signal = "BUY"
    elif trend == "DOWN" and last_rsi < 45:
        signal = "SELL"
    else:
        signal = "HOLD"

    return dict(
        signal=signal,
        last_close=round(last_close, 2),
        ema_fast=round(last_fast,  2),
        ema_slow=round(last_slow,  2),
        rsi=round(last_rsi,   1),
        trend=trend,
    )


def analyse_watchlist() -> pd.DataFrame:
    """
    Run generate_signal() for every stock in the watchlist.

    Loads close prices from the DB via price_data.load().

    Returns a DataFrame with columns:
      ticker, name, signal, last_close, ema_fast, ema_slow, rsi, trend
    """
    conn = db.get_conn()
    watchlist = pd.read_sql_query(
        "SELECT ID, ticker, name FROM stock ORDER BY ticker", conn
    )
    conn.close()

    records = []
    for _, row in watchlist.iterrows():
        df = pd_module.load(row["ticker"])

        if df.empty:
            records.append(
                dict(ticker=row["ticker"], name=row["name"],
                     signal="NO DATA", last_close=None,
                     ema_fast=None, ema_slow=None, rsi=None, trend=None)
            )
            continue

        result = generate_signal(df["close"])
        records.append(dict(ticker=row["ticker"], name=row["name"], **result))

    return pd.DataFrame(records)
