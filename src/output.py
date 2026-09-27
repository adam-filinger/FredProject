"""
output.py - Format and print the watchlist signal report to the console.

Public API
----------
print_report(signals_df, financials_df=None) -> None
"""

import pandas as pd
from datetime import datetime


_SIGNAL_EMOJI = {
    "BUY":               "BUY  [+]",
    "SELL":              "SELL [-]",
    "HOLD":              "HOLD [~]",
    "NO DATA":           "NO DATA",
    "INSUFFICIENT DATA": "INSUFFICIENT DATA",
}

# Key financial metrics to show alongside the signal (when financials_df is provided)
_FIN_COLS = [
    ("trailing_pe",    "P/E (TTM)"),
    ("forward_pe",     "P/E (Fwd)"),
    ("profit_margins", "Net Margin"),
    ("return_on_equity","ROE"),
    ("revenue_growth", "Rev Growth"),
    ("debt_to_equity", "D/E Ratio"),
    ("recommendation_key", "Analyst"),
    ("target_mean_price",  "Target $"),
]


def _fmt(val, pct: bool = False, dollars: bool = False) -> str:
    """Format a numeric value for display."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "n/a"
    if isinstance(val, str):
        return val
    if pct:
        return f"{val * 100:.1f}%"
    if dollars:
        return f"${val:,.2f}"
    return f"{val:,.2f}"


def print_report(
    signals_df: pd.DataFrame,
    financials_df: pd.DataFrame | None = None,
) -> None:
    """
    Print a formatted markdown-style signal report to the console.

    Parameters
    ----------
    signals_df    : output of quant.analyse_watchlist()
    financials_df : output of financials.load_latest() (optional, adds key metrics)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    width = 72

    print("=" * width)
    print(f"  MacroScope Signal Report -- {now}")
    print("=" * width)

    if signals_df.empty:
        print("  No watchlist data available.")
        print("=" * width)
        return

    # If financials pivot is provided, flatten it (columns = tickers) -> lookup by ticker
    fin_lookup: dict = {}
    if financials_df is not None and not financials_df.empty:
        # load_latest() returns a pivot: index=metric, cols=ticker
        # Transpose back so we can look up by ticker
        for ticker in financials_df.columns:
            fin_lookup[ticker] = financials_df[ticker].to_dict()

    for _, row in signals_df.iterrows():
        ticker = row["ticker"]
        name   = row.get("name", "")
        signal = row.get("signal", "n/a")
        label  = _SIGNAL_EMOJI.get(signal, signal)

        print(f"\n  {ticker:<8} {name}")
        print(f"  {'Signal':<18} {label}")

        if row.get("last_close") is not None:
            print(f"  {'Last Close':<18} {_fmt(row['last_close'], dollars=True)}")
            print(f"  {'EMA(20)':<18} {_fmt(row['ema_fast'], dollars=True)}")
            print(f"  {'EMA(50)':<18} {_fmt(row['ema_slow'], dollars=True)}")
            print(f"  {'RSI(14)':<18} {_fmt(row['rsi'])}")
            print(f"  {'Trend':<18} {row.get('trend', 'n/a')}")

        # Optional: key fundamentals
        if ticker in fin_lookup:
            fin = fin_lookup[ticker]
            print(f"  {'-- Fundamentals --'}")
            pct_fields = {"profit_margins", "return_on_equity", "revenue_growth"}
            dollar_fields = {"target_mean_price"}
            for col, label_fin in _FIN_COLS:
                val = fin.get(col)
                is_pct    = col in pct_fields
                is_dollar = col in dollar_fields
                print(f"  {label_fin:<18} {_fmt(val, pct=is_pct, dollars=is_dollar)}")

        print(f"  {'-' * (width - 2)}")

    print("=" * width)
    print()
