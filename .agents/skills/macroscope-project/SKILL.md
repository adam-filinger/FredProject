---
name: macroscope-project
description: >-
  Use this skill whenever working on the MacroScope project (FredProject).
  Contains the full architecture, module contracts, DB schema, design decisions,
  and file layout so the agent can immediately orient itself without re-exploring
  the codebase. Activate for any task involving: adding new modules, modifying
  the DB schema, understanding data flow, debugging the pipeline, or planning
  extensions.
---

# MacroScope Project – Architecture & Reference

## Project Overview

MacroScope is a stock analysis pipeline built in Python.
It downloads and stores watchlist stock data from yfinance, computes
technical signals (BUY/HOLD/SELL), and outputs a formatted console report.

- **Database**: SQLite (`macroscope.db` at project root)
- **Language**: Python 3.14 (`.venv`)
- **Entry point**: `python src/integration.py`
- **Notebook**: `yfin.ipynb` (exploration/prototyping — self-contained, parallel to modules)
- **Notebook setup cell**: prepends `src/` to `sys.path` so all modules can be imported directly

---

## Directory Layout

```
FredProject/
├── macroscope.db          ← SQLite database (all persistent state)
├── yfin.ipynb             ← Prototyping notebook (imports from src/)
├── pyproject.toml
├── requirements.txt
├── .env                   ← FRED_API_KEY (not for yfinance pipeline)
├── data/                  ← (reserved for future CSV/HTML exports)
├── src/
│   ├── db.py              ← Shared DB layer (get_conn, init_all_tables)
│   ├── watchlist.py       ← add/remove/get_all stocks
│   ├── price_data.py      ← Hourly price download & storage
│   ├── financials.py      ← .info fundamentals snapshots
│   ├── quant.py           ← EMA/RSI signals
│   ├── output.py          ← Console report formatter
│   ├── integration.py     ← Pipeline orchestrator (run all)
│   ├── trades.py          ← Executed orders ledger & FIFO P&L calculator
│   └── _old/              ← Archived FRED/Streamlit files (not in use)
│       ├── app.py
│       ├── charts.py
│       ├── data_fetcher.py
│       └── database.py
└── .agents/
    └── skills/
        ├── macroscope-project/   ← This skill
        └── yfinance-pipeline/    ← yfinance patterns skill
```

---

## DB Schema

### `stock` (watchlist)
```sql
CREATE TABLE stock (
    ID           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    currency     TEXT,
    last_updated TEXT,
    ticker       TEXT       -- yfinance symbol, e.g. "AAPL" (added via migration)
);
```

### `price_data`
```sql
CREATE TABLE price_data (
    stock_id INTEGER NOT NULL,
    time     TEXT    NOT NULL,   -- UTC ISO-8601 timestamp
    price    INTEGER NOT NULL,   -- close price as integer CENTS (×100)
    FOREIGN KEY (stock_id) REFERENCES stock(ID),
    PRIMARY KEY (stock_id, time)
);
```
> **Important**: prices are stored as integer cents. Divide by 100 to get real price.
> Use `INSERT OR IGNORE` when inserting — the composite PK prevents duplicates.

### `executed_orders`
```sql
CREATE TABLE executed_orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id      INTEGER NOT NULL,
    ticker        TEXT    NOT NULL,
    side          TEXT    NOT NULL CHECK(side IN ('BUY', 'SELL')),
    executed_at   TEXT    NOT NULL,   -- UTC ISO-8601 timestamp
    quantity      REAL    NOT NULL,   -- shares (fractional allowed)
    price_cents   INTEGER NOT NULL,   -- execution price in integer cents (×100)
    fee_cents     INTEGER NOT NULL DEFAULT 0,  -- commission in integer cents
    notes         TEXT,
    FOREIGN KEY (stock_id) REFERENCES stock(ID)
);
```
> **Important**: prices stored as integer cents — divide by 100 for real price.
> No UNIQUE constraint — the same ticker can be traded multiple times.

### `stock_financials`
```sql
CREATE TABLE stock_financials (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id      INTEGER NOT NULL,
    snapshot_date TEXT    NOT NULL,   -- ISO date "YYYY-MM-DD"
    -- 53 REAL/TEXT columns covering valuation, profitability, growth,
    -- income, balance sheet, per-share, dividends, risk, analyst targets
    FOREIGN KEY (stock_id) REFERENCES stock(ID),
    UNIQUE (stock_id, snapshot_date)   -- one snapshot per stock per day
);
```
See `src/db.py` for the full column list grouped by category.

---

## Module Contracts

### `db.py`
| Function | Returns | Notes |
|----------|---------|-------|
| `get_conn()` | `sqlite3.Connection` | FK enforcement always on |
| `init_all_tables()` | `None` | Idempotent; runs ticker migration |

### `watchlist.py`
| Function | Signature | Notes |
|----------|-----------|-------|
| `add` | `(ticker, name=None, currency='USD')` | Auto-fetches name from yfinance |
| `remove` | `(ticker)` | Cascades — deletes price_data + stock_financials rows too |
| `get_all` | `() → pd.DataFrame` | Columns: ID, ticker, name, currency, last_updated |

### `price_data.py`
| Function | Signature | Notes |
|----------|-----------|-------|
| `update_all` | `()` | Incremental for all watchlist stocks |
| `download_and_save` | `(ticker, stock_id) → int` | Returns rows inserted |
| `load` | `(ticker) → pd.DataFrame` | index=UTC datetime, col='close' (float dollars) |

**Incremental strategy**: fetches from `MAX(time)` date onwards; uses `INSERT OR IGNORE` for overlap safety.

### `financials.py`
| Function | Signature | Notes |
|----------|-----------|-------|
| `update_all` | `()` | Today's snapshot for all stocks; skips if exists |
| `save_snapshot` | `(stock_id, ticker, date) → bool` | Returns True if inserted |
| `load_latest` | `() → pd.DataFrame` | Pivoted: index=metric, cols=tickers |
| `load_history` | `(ticker) → pd.DataFrame` | index=snapshot_date |

**Field map**: `INFO_FIELD_MAP` dict in `financials.py` maps 53 DB columns to yfinance `.info` keys.

### `quant.py`

**Legacy API** (used by integration.py / output.py pipeline):

| Function | Signature | Notes |
|----------|-----------|-------|
| `compute_ema` | `(series, span) → pd.Series` | |
| `compute_rsi` | `(series, period=14) → pd.Series` | Wilder's RSI via ewm |
| `generate_signal` | `(close) → dict` | Returns signal, last_close, ema_fast, ema_slow, rsi, trend |
| `analyse_watchlist` | `() → pd.DataFrame` | All stocks × all signal fields |

**Signal logic** (legacy):
- `BUY`:  EMA(20) > EMA(50)  AND  40 < RSI < 70
- `SELL`: EMA(20) < EMA(50)  AND  RSI < 45
- `HOLD`: everything else
- `INSUFFICIENT DATA`: fewer than 64 rows available

**Quantitative algorithm classes** (spec §1.1–§3.2):

| Class | Category | `.run()` Inputs | Key Outputs |
|-------|----------|-----------------|-------------|
| `DualEMACrossover` | Momentum | `close_prices` | signal array (+1/-1/0), ema_short, ema_long |
| `DonchianBreakout` | Momentum | `high, low, close` | signal array, upper/lower channel |
| `PairsTradingZScore` | Mean-Reversion | `prices_a, prices_b` | spread, z_score, weight_a/b, beta, adf_pvalue |
| `BollingerBands` | Mean-Reversion | `close_prices` | signal array, middle/upper/lower band |
| `ARIMAGARCHModel` | Econometrics | `close_prices` | forecast_return, forecast_volatility, position_size |
| `RandomForestSignal` | ML | `ohlcv DataFrame` | probability_up, signal |

**Dependencies**: scikit-learn, statsmodels, arch (in requirements.txt).
**Helper**: `fetch_ohlcv(ticker)` downloads OHLCV from yfinance for algorithms needing H/L/V.

### `trades.py`
| Function | Signature | Notes |
|----------|-----------|-------|
| `record_order` | `(ticker, side, quantity, price, executed_at=None, fee=0.0, notes=None) → int` | Inserts one BUY/SELL order; returns new row id |
| `load` | `(ticker) → pd.DataFrame` | All orders for one ticker; prices in dollars |
| `load_all` | `() → pd.DataFrame` | All orders for all tickers |
| `pnl_by_ticker` | `() → pd.DataFrame` | FIFO P&L per ticker: realised_pnl, open_qty, avg_cost, total_fees, total_invested |
| `pnl_all` | `(use_live_prices=True) → pd.DataFrame` | Full portfolio P&L incl. unrealised (mark-to-market via price_data.load) |
| `print_pnl_report` | `(use_live_prices=True)` | Formatted console P&L report |

**P&L method**: FIFO — oldest BUY lots matched first against SELL orders.  
**Fee allocation**: buy-side fee added to cost/share; sell-side fee deducted from proceeds/share.

### `output.py`
| Function | Signature | Notes |
|----------|-----------|-------|
| `print_report` | `(signals_df, financials_df=None)` | `financials_df` = output of `financials.load_latest()` |

### `integration.py`
| Function | Signature | Notes |
|----------|-----------|-------|
| `update_all` | `(skip_prices=False, skip_financials=False)` | Full pipeline: init → prices → financials → signals → report |

---

## Data Flow

```
watchlist.add("AAPL")
        │
        ▼
   stock table
        │
   ┌────┴──────┐
   ▼           ▼
price_data  financials
(hourly)    (.info snap)
   │           │
   └─────┬─────┘
         ▼
       quant
    (EMA/RSI signals)
         │
         ▼
       output
    (console report)
         ▲
   integration.update_all()

trades.record_order("AAPL", "BUY", ...)
        │
        ▼
  executed_orders table
        │
  trades.pnl_all()  ← also reads price_data for mark-to-market
        │
  trades.print_pnl_report()
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Price storage | Integer cents (`price * 100`) | Avoids float precision drift; matches `INTEGER` column |
| Financials cadence | One snapshot per stock per day | `UNIQUE(stock_id, snapshot_date)` — safe to re-run |
| Incremental updates | Fetch from `MAX(time)` date | Avoids re-downloading all history every run |
| Shared DB layer | `db.py` (separate from old `database.py`) | Single connection pattern; old file left untouched |
| Notebook role | Self-contained exploration | No coupling; `sys.path.insert(0, 'src/')` in first cell |
| FRED/Streamlit files | Archived to `src/_old/` | Not in use; preserved for reference |
| Entry point | `python src/integration.py` | Simple; no CLI framework; `skip_*` flags for partial runs |

---

## Common Patterns

### Adding a new watchlist stock
```python
import sys; sys.path.insert(0, "src")
import watchlist, integration
watchlist.add("TSLA")
integration.update_all()   # download prices + financials + signal
```

### Running signals only (no network)
```python
import quant, financials, output
signals = quant.analyse_watchlist()
output.print_report(signals, financials_df=financials.load_latest())
```

### Prices only update
```python
integration.update_all(skip_financials=True)
```

### Loading data for analysis
```python
import price_data, financials
df = price_data.load("NVDA")          # hourly closes
hist = financials.load_history("NVDA") # all fundamental snapshots
```

---

## Extending the Project

When adding a **new module** (`src/new_module.py`):
1. Import `db` (not `database`) for DB access.
2. Call `db.get_conn()` for connections — never open `sqlite3.connect()` directly.
3. If you need a new table: add `CREATE TABLE IF NOT EXISTS` to `db.init_all_tables()`.
4. Wire the new module into `integration.update_all()` as a new numbered step.
5. Export `load()` or `load_latest()` functions so `output.py` can consume data.

When adding a **new financial field** to `stock_financials`:
1. Add the column to `db.init_all_tables()` (use `ALTER TABLE` migration pattern for live DBs).
2. Add the mapping to `INFO_FIELD_MAP` in `financials.py`.
3. Re-run `financials.update_all()` — new snapshots will include the field.

---

## Maintenance

This skill must be kept up to date whenever the project structure changes.
The rule in `.agents/rules/skill-maintenance.md` defines exactly when and what
to update — read it for the full trigger list.

**Quick checklist after any change:**
- [ ] Directory layout reflects the actual `src/` structure
- [ ] Module contracts table matches current public function signatures
- [ ] DB schema matches `db.init_all_tables()` and the live `macroscope.db`
- [ ] Data flow diagram reflects any new modules added to `integration.py`
- [ ] Key design decisions table is updated if a decision was reversed or extended
- [ ] Common patterns section has copy-pasteable examples for any new workflow
