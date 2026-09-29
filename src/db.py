"""
db.py - Shared database layer for the MacroScope yfinance pipeline.

All new modules (watchlist, price_data, financials, quant, output, integration,
trades) import from here instead of opening their own connections.

The existing database.py is left untouched (used by the Streamlit/FRED side).
"""

import sqlite3
import os

# Resolve DB path relative to the project root (one level up from src/)
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)
DB_FILE = os.path.join(_PROJECT_ROOT, "macroscope.db")


def get_conn() -> sqlite3.Connection:
    """
    Return a configured SQLite connection.
    Foreign-key enforcement is always enabled.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_all_tables() -> None:
    """
    Create all yfinance pipeline tables if they do not already exist,
    and run any lightweight column migrations (e.g. adding 'ticker' to stock).

    Safe to call multiple times -- all statements are idempotent.
    """
    conn = get_conn()
    cur = conn.cursor()

    # stock (watchlist)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            ID           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT,
            currency     TEXT,
            last_updated TEXT
        )
    """)

    # Migration: add ticker column if missing
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(stock)")}
    if "ticker" not in existing_cols:
        cur.execute("ALTER TABLE stock ADD COLUMN ticker TEXT")

    # price_data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_data (
            stock_id INTEGER NOT NULL,
            time     TEXT    NOT NULL,
            price    INTEGER NOT NULL,
            FOREIGN KEY (stock_id) REFERENCES stock(ID),
            PRIMARY KEY (stock_id, time)
        )
    """)

    # stock_financials
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_financials (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id                  INTEGER NOT NULL,
            snapshot_date             TEXT    NOT NULL,
            market_cap                REAL, enterprise_value          REAL,
            trailing_pe               REAL, forward_pe                REAL,
            peg_ratio                 REAL, price_to_book             REAL,
            price_to_sales_ttm        REAL, ev_to_revenue             REAL,
            ev_to_ebitda              REAL,
            profit_margins            REAL, gross_margins             REAL,
            ebitda_margins            REAL, operating_margins         REAL,
            return_on_assets          REAL, return_on_equity          REAL,
            earnings_growth           REAL, revenue_growth            REAL,
            earnings_quarterly_growth REAL,
            total_revenue             REAL, gross_profits             REAL,
            ebitda                    REAL, net_income                REAL,
            free_cashflow             REAL, operating_cashflow        REAL,
            total_cash                REAL, total_cash_per_share      REAL,
            total_debt                REAL, debt_to_equity            REAL,
            quick_ratio               REAL, current_ratio             REAL,
            trailing_eps              REAL, forward_eps               REAL,
            book_value                REAL, revenue_per_share         REAL,
            dividend_rate             REAL, dividend_yield            REAL,
            payout_ratio              REAL, five_year_avg_div_yield   REAL,
            beta                      REAL, fifty_two_week_high       REAL,
            fifty_two_week_low        REAL, shares_outstanding        REAL,
            float_shares              REAL, shares_short              REAL,
            short_ratio               REAL, short_percent_of_float    REAL,
            target_high_price         REAL, target_low_price          REAL,
            target_mean_price         REAL, target_median_price       REAL,
            recommendation_key        TEXT, recommendation_mean       REAL,
            num_analyst_opinions      INTEGER,
            FOREIGN KEY (stock_id) REFERENCES stock(ID),
            UNIQUE (stock_id, snapshot_date)
        )
    """)

    # executed_orders (buy & sell trades for P&L tracking)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS executed_orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id      INTEGER NOT NULL,
            ticker        TEXT    NOT NULL,
            side          TEXT    NOT NULL CHECK(side IN ('BUY', 'SELL')),
            executed_at   TEXT    NOT NULL,   -- UTC ISO-8601 timestamp
            quantity      REAL    NOT NULL,   -- number of shares (fractional allowed)
            price_cents   INTEGER NOT NULL,   -- execution price in integer cents (x100)
            fee_cents     INTEGER NOT NULL DEFAULT 0,  -- commission/fee in integer cents
            notes         TEXT,
            FOREIGN KEY (stock_id) REFERENCES stock(ID)
        )
    """)

    conn.commit()
    conn.close()
