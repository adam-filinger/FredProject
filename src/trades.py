"""
trades.py - Executed orders ledger and FIFO profit/loss calculator.

This module records buy and sell orders for watchlist stocks and
computes realised and unrealised profit/loss using FIFO matching.

Prices are stored internally as integer cents (× 100), consistent
with the price_data table convention.  All public-facing values
(DataFrames, print_pnl_report) use decimal dollars/currency units.

Public API
----------
record_order(ticker, side, quantity, price, executed_at, fee, notes)
    Insert one executed order into the database.

load(ticker)
    Return all orders for a single ticker as a DataFrame.

load_all()
    Return all orders for every ticker as a DataFrame.

pnl_by_ticker()
    FIFO P&L summary per ticker (realised P&L, open lots, avg cost).

pnl_all(use_live_prices=True)
    Full portfolio P&L: realised + unrealised (mark-to-market).

print_pnl_report(use_live_prices=True)
    Formatted console report.
"""

import sys
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

# Ensure src/ is importable when run as a script
_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_cents(price: float) -> int:
    """Convert a decimal price (dollars) to integer cents."""
    return round(price * 100)


def _to_dollars(cents: int) -> float:
    """Convert integer cents to decimal dollars."""
    return cents / 100.0


def _resolve_stock_id(cur, ticker: str) -> int:
    """
    Return the stock.ID for *ticker*.
    Raises ValueError if the ticker is not in the watchlist.
    """
    row = cur.execute(
        "SELECT ID FROM stock WHERE ticker = ?", (ticker.upper(),)
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Ticker '{ticker}' not found in the watchlist. "
            "Add it first with watchlist.add() before recording orders."
        )
    return row[0]


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def record_order(
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    executed_at: Optional[str] = None,
    fee: float = 0.0,
    notes: Optional[str] = None,
) -> int:
    """
    Insert one executed order into the database.

    Parameters
    ----------
    ticker      : stock ticker, e.g. "AAPL"
    side        : "BUY" or "SELL" (case-insensitive)
    quantity    : number of shares (fractional shares are supported)
    price       : execution price per share in decimal dollars/currency
    executed_at : UTC ISO-8601 timestamp string; defaults to now if omitted
    fee         : total commission/fee in decimal dollars (default 0)
    notes       : optional free-text comment

    Returns
    -------
    int : the row id (executed_orders.id) of the newly inserted order
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be 'BUY' or 'SELL', got '{side}'")
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity}")
    if price < 0:
        raise ValueError(f"price must be non-negative, got {price}")

    executed_at = executed_at or _now_utc()
    price_cents = _to_cents(price)
    fee_cents = _to_cents(fee)

    conn = db.get_conn()
    try:
        cur = conn.cursor()
        stock_id = _resolve_stock_id(cur, ticker)
        cur.execute(
            """
            INSERT INTO executed_orders
                (stock_id, ticker, side, executed_at, quantity, price_cents, fee_cents, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (stock_id, ticker.upper(), side, executed_at,
             quantity, price_cents, fee_cents, notes),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def load(ticker: str) -> pd.DataFrame:
    """
    Return all executed orders for *ticker* as a DataFrame.

    Columns
    -------
    id, stock_id, ticker, side, executed_at, quantity,
    price (dollars), fee (dollars), notes
    """
    conn = db.get_conn()
    try:
        df = pd.read_sql_query(
            """
            SELECT id, stock_id, ticker, side, executed_at, quantity,
                   price_cents, fee_cents, notes
            FROM executed_orders
            WHERE ticker = ?
            ORDER BY executed_at ASC
            """,
            conn,
            params=(ticker.upper(),),
        )
    finally:
        conn.close()

    if df.empty:
        return df

    df["price"] = df["price_cents"].apply(_to_dollars)
    df["fee"] = df["fee_cents"].apply(_to_dollars)
    df = df.drop(columns=["price_cents", "fee_cents"])
    df["executed_at"] = pd.to_datetime(df["executed_at"], utc=True)
    return df


def load_all() -> pd.DataFrame:
    """
    Return all executed orders for every ticker as a DataFrame.
    Columns are the same as load().
    """
    conn = db.get_conn()
    try:
        df = pd.read_sql_query(
            """
            SELECT id, stock_id, ticker, side, executed_at, quantity,
                   price_cents, fee_cents, notes
            FROM executed_orders
            ORDER BY ticker ASC, executed_at ASC
            """,
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        return df

    df["price"] = df["price_cents"].apply(_to_dollars)
    df["fee"] = df["fee_cents"].apply(_to_dollars)
    df = df.drop(columns=["price_cents", "fee_cents"])
    df["executed_at"] = pd.to_datetime(df["executed_at"], utc=True)
    return df


# ---------------------------------------------------------------------------
# FIFO P&L engine
# ---------------------------------------------------------------------------

def _fifo_pnl(orders: pd.DataFrame) -> dict:
    """
    Run FIFO matching on a single ticker's orders DataFrame.

    Parameters
    ----------
    orders : DataFrame with columns side, quantity, price, fee
             sorted by executed_at ASC (oldest first)

    Returns
    -------
    dict with keys:
        realised_pnl    : total realised P&L in dollars (after fees)
        open_lots       : list of dicts {qty, cost_per_share}
                          representing remaining open BUY positions
        total_open_qty  : total shares still held
        avg_cost        : weighted-average cost per open share (incl. fees)
        total_fees      : all fees paid (both sides)
    """
    # Each open lot: {'qty': float, 'cost_per_share': float}
    open_lots: list = []
    realised_pnl = 0.0
    total_fees = 0.0

    for _, row in orders.iterrows():
        side = row["side"]
        qty = float(row["quantity"])
        price = float(row["price"])
        fee = float(row["fee"])
        total_fees += fee

        if side == "BUY":
            # Cost-per-share includes the buy-side fee spread across shares
            cost_per_share = price + (fee / qty if qty else 0)
            open_lots.append({"qty": qty, "cost_per_share": cost_per_share})

        elif side == "SELL":
            # Net proceeds per share after sell-side fee
            proceeds_per_share = price - (fee / qty if qty else 0)
            remaining_sell_qty = qty

            while remaining_sell_qty > 1e-9 and open_lots:
                lot = open_lots[0]
                matched_qty = min(lot["qty"], remaining_sell_qty)

                # Realised P&L for this matched portion
                realised_pnl += matched_qty * (proceeds_per_share - lot["cost_per_share"])

                lot["qty"] -= matched_qty
                remaining_sell_qty -= matched_qty

                if lot["qty"] < 1e-9:
                    open_lots.pop(0)

            # If we sold more than we bought (short selling not modelled here),
            # warn and ignore the excess
            if remaining_sell_qty > 1e-9:
                print(
                    f"[trades] Warning: SELL quantity exceeds known open BUY lots "
                    f"by {remaining_sell_qty:.4f} shares. Excess ignored in P&L."
                )

    # Summarise open position
    total_open_qty = sum(lot["qty"] for lot in open_lots)
    if total_open_qty > 1e-9:
        avg_cost = (
            sum(lot["qty"] * lot["cost_per_share"] for lot in open_lots)
            / total_open_qty
        )
    else:
        avg_cost = 0.0

    return {
        "realised_pnl": round(realised_pnl, 4),
        "open_lots": open_lots,
        "total_open_qty": round(total_open_qty, 6),
        "avg_cost": round(avg_cost, 4),
        "total_fees": round(total_fees, 4),
    }


# ---------------------------------------------------------------------------
# Summary functions
# ---------------------------------------------------------------------------

def pnl_by_ticker() -> pd.DataFrame:
    """
    Compute FIFO P&L for every ticker that has executed orders.

    Returns
    -------
    DataFrame indexed by ticker with columns:
        realised_pnl    : realised gain/loss in dollars (after fees)
        open_qty        : shares currently held
        avg_cost        : average cost per open share (incl. buy-side fees)
        total_fees      : all fees paid (buy + sell side)
        total_invested  : avg_cost x open_qty  (current book value of position)
    """
    all_orders = load_all()
    if all_orders.empty:
        return pd.DataFrame(
            columns=["ticker", "realised_pnl", "open_qty",
                     "avg_cost", "total_fees", "total_invested"]
        ).set_index("ticker")

    records = []
    for ticker, group in all_orders.groupby("ticker"):
        result = _fifo_pnl(group.reset_index(drop=True))
        invested = result["avg_cost"] * result["total_open_qty"]
        records.append({
            "ticker": ticker,
            "realised_pnl": result["realised_pnl"],
            "open_qty": result["total_open_qty"],
            "avg_cost": result["avg_cost"],
            "total_fees": result["total_fees"],
            "total_invested": round(invested, 4),
        })

    df = pd.DataFrame(records).set_index("ticker")
    return df


def pnl_all(use_live_prices: bool = True) -> pd.DataFrame:
    """
    Full portfolio P&L: realised + unrealised (mark-to-market).

    Parameters
    ----------
    use_live_prices : if True, fetch the most recent close from price_data
                      for mark-to-market unrealised P&L.
                      If False, unrealised_pnl and current_price columns
                      will be NaN.

    Returns
    -------
    DataFrame indexed by ticker with columns:
        realised_pnl    : realised gain/loss in dollars
        open_qty        : shares still held
        avg_cost        : average cost per open share
        total_fees      : all fees paid
        total_invested  : book value of open position
        current_price   : most recent close price (if use_live_prices=True)
        market_value    : open_qty x current_price
        unrealised_pnl  : market_value - total_invested
        total_pnl       : realised_pnl + unrealised_pnl
    """
    summary = pnl_by_ticker()
    if summary.empty:
        return summary

    if not use_live_prices:
        summary["current_price"] = float("nan")
        summary["market_value"] = float("nan")
        summary["unrealised_pnl"] = float("nan")
        summary["total_pnl"] = summary["realised_pnl"]
        return summary

    # Lazily import price_data to avoid circular imports
    import price_data as pd_module

    current_prices = {}
    for ticker in summary.index:
        try:
            closes = pd_module.load(ticker)
            if not closes.empty:
                current_prices[ticker] = float(closes["close"].iloc[-1])
        except Exception:
            current_prices[ticker] = float("nan")

    summary["current_price"] = summary.index.map(
        lambda t: current_prices.get(t, float("nan"))
    )
    summary["market_value"] = summary["open_qty"] * summary["current_price"]
    summary["unrealised_pnl"] = (
        summary["market_value"] - summary["total_invested"]
    )
    summary["total_pnl"] = summary["realised_pnl"] + summary["unrealised_pnl"]

    # Round monetary columns
    for col in ["market_value", "unrealised_pnl", "total_pnl"]:
        summary[col] = summary[col].round(4)

    return summary


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

def print_pnl_report(use_live_prices: bool = True) -> None:
    """
    Print a formatted P&L report to the console.

    Parameters
    ----------
    use_live_prices : mark-to-market unrealised P&L if True
    """
    df = pnl_all(use_live_prices=use_live_prices)

    header = "=" * 70
    print(f"\n{header}")
    print(f"  MacroScope -- Portfolio P&L Report")
    print(f"  Generated: {_now_utc()}")
    print(f"{header}")

    if df.empty:
        print("  No executed orders recorded yet.")
        print(header)
        return

    for ticker, row in df.iterrows():
        pnl_symbol = "+" if row["realised_pnl"] >= 0 else "-"
        print(f"\n  {ticker}")
        print(f"    Open position : {row['open_qty']:.4f} shares @ avg cost ${row['avg_cost']:.2f}")
        print(f"    Total invested: ${row['total_invested']:.2f}")
        print(f"    Total fees    : ${row['total_fees']:.2f}")
        print(f"    Realised P&L  : {pnl_symbol} ${abs(row['realised_pnl']):.2f}")

        if use_live_prices and not pd.isna(row.get("current_price")):
            upnl_sym = "+" if row["unrealised_pnl"] >= 0 else "-"
            tpnl_sym = "+" if row["total_pnl"] >= 0 else "-"
            print(f"    Current price : ${row['current_price']:.2f}")
            print(f"    Market value  : ${row['market_value']:.2f}")
            print(f"    Unrealised P&L: {upnl_sym} ${abs(row['unrealised_pnl']):.2f}")
            print(f"    Total P&L     : {tpnl_sym} ${abs(row['total_pnl']):.2f}")

    # Portfolio totals
    print(f"\n{'-' * 70}")
    print(f"  PORTFOLIO TOTALS")
    print(f"    Total fees paid : ${df['total_fees'].sum():.2f}")
    total_real = df['realised_pnl'].sum()
    print(f"    Total realised  : {'+'if total_real >= 0 else '-'} ${abs(total_real):.2f}")
    if use_live_prices:
        total_unr = df["unrealised_pnl"].sum()
        total_pnl = df["total_pnl"].sum()
        print(f"    Total unrealised: {'+'if total_unr >= 0 else '-'} ${abs(total_unr):.2f}")
        print(f"    Grand total P&L : {'+'if total_pnl >= 0 else '-'} ${abs(total_pnl):.2f}")
    print(header)


# ---------------------------------------------------------------------------
# Script entry point (quick smoke test / demo)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_all_tables()
    print_pnl_report()
