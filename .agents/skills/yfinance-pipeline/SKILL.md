---
name: yfinance-pipeline
description: >-
  Use this skill when writing or modifying any code that uses the yfinance
  library in the MacroScope project. Covers the correct API usage patterns,
  known gotchas (multi-level column headers, timezone handling, data gaps),
  incremental download strategies, and how each yfinance data source maps
  to the MacroScope DB schema. Activate for tasks involving: downloading price
  history, fetching .info fundamentals, working with earnings/financials data,
  or debugging yfinance-related issues.
---

# yfinance Pipeline – Patterns & Gotchas

## Installed Version

```bash
# Check version
.venv/bin/python -c "import yfinance; print(yfinance.__version__)"
```

---

## Data Sources Available

| yfinance attribute | What it returns | Stored in MacroScope? |
|---|---|---|
| `Ticker.history(period, interval)` | OHLCV + Dividends + Stock Splits | ✅ `price_data` (Close only) |
| `Ticker.info` | ~150 fundamental fields dict | ✅ `stock_financials` (53 fields) |
| `Ticker.financials` | Annual income statement | ❌ (not yet) |
| `Ticker.quarterly_financials` | Quarterly income statement | ❌ (not yet) |
| `Ticker.balance_sheet` | Annual balance sheet | ❌ (not yet) |
| `Ticker.cashflow` | Annual cash flow statement | ❌ (not yet) |
| `Ticker.earnings_dates` | Past & upcoming earnings | ❌ (not yet) |
| `Ticker.recommendations` | Analyst buy/hold/sell counts | ❌ (not yet) |

---

## Price History – Correct Usage

### Preferred pattern (used in `price_data.py`)
```python
import yfinance as yf

# Single ticker — always use Ticker.history(), NOT yf.download() for pipelines
hist = yf.Ticker("AAPL").history(period="730d", interval="1h")
# Returns: DataFrame with index=Datetime (tz-aware), cols: Open, High, Low, Close, Volume, Dividends, Stock Splits
```

### Incremental fetch (start date)
```python
hist = yf.Ticker("AAPL").history(start="2026-09-01", interval="1h")
# 'start' accepts "YYYY-MM-DD" string
```

### ⚠️ Known gotchas

**1. Multi-level column headers with `yf.download()`**
When using `yf.download(tickers=["AAPL","MSFT"])`, the result has a MultiIndex
column (`Price`, `Ticker`). The `Ticker.history()` method returns a flat
DataFrame — always prefer it for single-ticker pipelines.

**2. Timezone handling**
`history()` returns a tz-aware DatetimeIndex (exchange local time, e.g. `US/Eastern`).
Always convert to UTC before storing:
```python
hist.index = pd.DatetimeIndex(hist.index).tz_convert("UTC")
ts_str = ts.isoformat()  # "2026-09-25T13:30:00+00:00"
```

**3. Hourly data limit**
yfinance only returns up to **730 days** of hourly (1h) data.
Use `period="730d"` for the initial full fetch. For longer history, switch to `interval="1d"`.

**4. First candle volume = 0**
The very first row returned often has `Volume = 0`. This is a yfinance artifact —
filter if volume is needed for analysis but not an issue for close-price storage.

**5. Empty response on market holidays / weekends**
`hist.empty` will be True for non-trading periods. Always guard:
```python
if hist.empty:
    return 0
```

**6. Overlap on incremental fetch**
When fetching `start=last_stored_date`, yfinance may return rows already in the DB.
Guard with:
```python
if last_time and ts_str <= last_time:
    continue
```
Combined with `INSERT OR IGNORE` (composite PK) for double safety.

---

## Fundamentals (.info) – Correct Usage

```python
info = yf.Ticker("AAPL").info
# Returns: dict with ~150 keys (varies by ticker type and market)
```

### Validity check
```python
if not info or info.get("quoteType") is None:
    # Empty or invalid response — ticker may be delisted or wrong symbol
    return None
```

### Numeric field casting
All numeric fields should be explicitly cast — some fields return `int`, some `float`,
some `None` when unavailable. Use a safe cast:
```python
try:
    val = float(info.get("marketCap"))
except (TypeError, ValueError):
    val = None
```

### Key .info fields mapped in MacroScope (`INFO_FIELD_MAP` in `financials.py`)

| Category | yfinance key | DB column |
|---|---|---|
| Valuation | `marketCap` | `market_cap` |
| Valuation | `trailingPE` | `trailing_pe` |
| Valuation | `forwardPE` | `forward_pe` |
| Profitability | `profitMargins` | `profit_margins` |
| Profitability | `returnOnEquity` | `return_on_equity` |
| Growth | `revenueGrowth` | `revenue_growth` |
| Income | `totalRevenue` | `total_revenue` |
| Income | `freeCashflow` | `free_cashflow` |
| Balance Sheet | `totalDebt` | `total_debt` |
| Balance Sheet | `debtToEquity` | `debt_to_equity` |
| Analyst | `recommendationKey` | `recommendation_key` |
| Analyst | `targetMeanPrice` | `target_mean_price` |

Full map: see `src/financials.py` → `INFO_FIELD_MAP`.

---

## Adding a New yfinance Data Source

To add e.g. **quarterly financials** as a new table:

1. **Explore the data first**:
   ```python
   t = yf.Ticker("AAPL")
   df = t.quarterly_financials
   print(df.index.tolist())   # available metrics
   print(df.columns.tolist()) # quarter dates
   ```

2. **Add a table** to `db.init_all_tables()` in `src/db.py`.

3. **Create a new module** (e.g. `src/quarterly.py`) following the same pattern as
   `financials.py`:
   - `_fetch(ticker)` → raw data
   - `save(stock_id, ticker)` → insert to DB
   - `update_all()` → loop watchlist
   - `load(ticker)` → read from DB

4. **Add it to `integration.update_all()`** as a new numbered step.

5. **Validate** by running `python src/integration.py` and checking the DB:
   ```bash
   sqlite3 macroscope.db "SELECT COUNT(*) FROM new_table;"
   ```

---

## Extending the Signal Algorithm (`quant.py`)

Current: EMA(20)/EMA(50) crossover + RSI(14).

To add a new indicator:
```python
# In quant.py, add a new helper:
def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd     = ema_fast - ema_slow
    signal_l = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_l

# Then incorporate into generate_signal():
# macd, signal_line = compute_macd(close)
# macd_bullish = macd.iloc[-1] > signal_line.iloc[-1]
```

To incorporate fundamentals into the signal, load from `financials.load_latest()`
and pass the pivot DataFrame as a parameter to `generate_signal()`.

---

## Running & Debugging

```bash
# Full pipeline
cd /Users/adamfilinger/FredProject
.venv/bin/python src/integration.py

# Just signals (no network)
.venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
import quant, financials, output
output.print_report(quant.analyse_watchlist(), financials.load_latest())
"

# Inspect DB tables
sqlite3 macroscope.db '.tables'
sqlite3 macroscope.db 'SELECT ticker, COUNT(*) as rows FROM stock s JOIN price_data p ON s.ID=p.stock_id GROUP BY ticker;'

# Check latest financials snapshot date
sqlite3 macroscope.db 'SELECT ticker, MAX(snapshot_date) FROM stock s JOIN stock_financials f ON s.ID=f.stock_id GROUP BY ticker;'
```

---

## Maintenance

This skill must be kept up to date whenever yfinance usage patterns change.
The rule in `.agents/rules/skill-maintenance.md` defines exactly when and what
to update.

**Quick checklist after any change:**
- [ ] Data sources table updated if a new yfinance attribute is stored
- [ ] `INFO_FIELD_MAP` excerpt reflects current keys in `financials.py`
- [ ] Any new gotcha or workaround discovered is added to the gotchas section
- [ ] "Adding a New Data Source" steps still match the current module pattern
- [ ] Debug commands still work against the current schema
