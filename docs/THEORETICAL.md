# MacroScope — Theoretical Documentation

> *A quantitative stock analysis and portfolio management platform built as the foundation for an intelligent, autonomous trading system.*

---

## Table of Contents

1. [Project Philosophy & Motivation](#1-project-philosophy--motivation)
2. [Project Evolution](#2-project-evolution)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Trading Concepts & Algorithm Theory](#4-trading-concepts--algorithm-theory)
   - 4.1 [The Legacy Pipeline Signal (EMA/RSI)](#41-the-legacy-pipeline-signal-emarsi)
   - 4.2 [Module 1: Trend-Following & Momentum](#42-module-1-trend-following--momentum)
   - 4.3 [Module 2: Mean-Reversion & Statistical Arbitrage](#43-module-2-mean-reversion--statistical-arbitrage)
   - 4.4 [Module 3: Econometrics & Machine Learning](#44-module-3-econometrics--machine-learning)
   - 4.5 [Algorithm Summary Matrix](#45-algorithm-summary-matrix)
5. [P&L Accounting Methodology](#5-pl-accounting-methodology)
6. [Overall Project Structure](#6-overall-project-structure)
7. [Vision & Roadmap](#7-vision--roadmap)

---

## 1. Project Philosophy & Motivation

MacroScope is being built as a **foundation for a future production-grade autonomous trading system**. The current version serves as the analytical and data infrastructure layer — a working pipeline that downloads live market data, computes quantitative trading signals, tracks executed orders, and calculates portfolio-level profit and loss.

The long-term vision extends far beyond technical analysis:

- **Automated signal generation** across multiple quantitative paradigms
- **Broker API integration** for programmatic order execution
- **Fundamental analysis** (DCF valuation models, balance sheet health scoring)
- **Sentiment analysis** (Reddit, financial forums, news feeds)
- **AI-powered research** for discovering investment opportunities and correlations
- **Portfolio-level hedging and risk management**

Today, MacroScope is a functional end-to-end pipeline: you add stocks to a watchlist, the system downloads hourly price data and fundamental snapshots, computes buy/hold/sell signals, and prints a formatted report. You can manually record executed trades and view FIFO-based profit and loss. The six advanced quantitative algorithms are implemented and tested but not yet wired into the automated pipeline — they exist as a toolkit for manual analysis and future integration.

---

## 2. Project Evolution

MacroScope began as a **macroeconomic data dashboard** built with Streamlit, Plotly, and the FRED (Federal Reserve Economic Data) API. That original system provided interactive visualization of macroeconomic indicators like GDP, CPI, and unemployment rates, with features including:

- Full-text search across 800,000+ FRED time-series
- Dynamic parameter configuration (units, frequency, aggregation)
- A hybrid hot/cold caching engine (RAM + SQLite) to manage FRED's 120 req/min rate limit
- Historical data revision tracking via the ALFRED API

The project then pivoted to focus on **individual stock analysis and trading** — shifting from macro-level economic indicators to stock-level price data, fundamental metrics, and quantitative trading signals. The FRED/Streamlit components are archived in `src/_old/` but not actively used. The current system is built around `yfinance` for market data, `SQLite` for persistence, and a modular Python pipeline architecture.

---

## 3. System Architecture Overview

MacroScope follows a **pipeline architecture** with clearly separated concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA INGESTION LAYER                      │
│  watchlist.py → price_data.py → financials.py               │
│  (manage stocks)  (hourly OHLCV)   (.info fundamentals)     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    ANALYSIS LAYER                            │
│  quant.py                                                   │
│  ├── Legacy: EMA/RSI signal (pipeline-integrated)           │
│  └── Advanced: 6 algorithm classes (standalone toolkit)     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    OUTPUT LAYER                              │
│  output.py → console signal report                          │
│  trades.py → order ledger + FIFO P&L report                 │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION                             │
│  integration.py → chains all steps in sequence              │
└─────────────────────────────────────────────────────────────┘
```

All modules share a single **SQLite database** (`macroscope.db`) accessed through a centralised database layer (`db.py`). The system is designed to be run either as a single pipeline invocation (`python src/integration.py`) or interactively through a Jupyter notebook or Python REPL.

---

## 4. Trading Concepts & Algorithm Theory

MacroScope implements seven distinct signal-generation approaches, organised into four categories by their underlying trading philosophy.

### 4.1 The Legacy Pipeline Signal (EMA/RSI)

This is the signal that currently drives the automated pipeline. It combines two of the most fundamental technical indicators into a single composite signal.

#### Exponential Moving Average (EMA) Crossover

An EMA gives more weight to recent prices, making it more responsive than a Simple Moving Average (SMA). MacroScope uses a **dual-EMA crossover** with periods of 20 (fast) and 50 (slow):

$$\text{EMA}_t = \alpha \cdot p_t + (1 - \alpha) \cdot \text{EMA}_{t-1}, \quad \alpha = \frac{2}{N+1}$$

When the fast EMA crosses above the slow EMA, it signals upward momentum. When it crosses below, momentum is shifting downward. The 20/50 combination was chosen as a balance between responsiveness and noise filtering — shorter periods (e.g., 5/10) generate too many false signals in choppy markets, while longer periods (e.g., 50/200) react too slowly for the hourly timeframe used.

#### Relative Strength Index (RSI)

RSI measures the velocity and magnitude of price movements on a 0–100 scale:

$$\text{RSI} = 100 - \frac{100}{1 + RS}, \quad RS = \frac{\text{Avg Gain}}{\text{Avg Loss}}$$

MacroScope uses Wilder's smoothing method (exponential moving average with α = 1/period) over a 14-period window, which is the industry standard established by J. Welles Wilder in his 1978 work *New Concepts in Technical Trading Systems*.

#### Composite Signal Logic

The EMA and RSI are combined as follows:

| Signal | Condition | Rationale |
|--------|-----------|-----------|
| **BUY** | EMA(20) > EMA(50) AND 40 < RSI < 70 | Trend is bullish and momentum is healthy — not yet overbought |
| **SELL** | EMA(20) < EMA(50) AND RSI < 45 | Trend is bearish and selling pressure is accelerating |
| **HOLD** | Everything else | Conflicting signals — no clear directional conviction |
| **INSUFFICIENT DATA** | Fewer than 64 price rows | Not enough history for reliable indicator computation |

**Parameter choices:**
- **RSI 40–70 for BUY**: The classic "overbought" threshold is 70. By capping at 70, the system avoids buying into exhausted rallies. The 40 floor prevents buying during bearish RSI territory where momentum hasn't confirmed.
- **RSI < 45 for SELL**: Slightly below the midpoint (50) to avoid premature sell signals during healthy consolidations.
- **64 minimum rows**: EMA(50) needs ≈50 bars to stabilise, plus 14 for RSI warmup.

> **Current Status**: This is the only signal integrated into the automated pipeline (`integration.py` → `quant.analyse_watchlist()` → `output.print_report()`).

---

### 4.2 Module 1: Trend-Following & Momentum

These algorithms assume that **existing price trends tend to persist** and seek to identify and ride those trends.

#### 4.2.1 Dual EMA Crossover (Advanced Version)

The advanced implementation (class `DualEMACrossover`) is a refined version of the legacy crossover with important differences:

**Mathematical formulation:**

1. **SMA-Seeded Initialisation**: Unlike the legacy `ewm(adjust=False)` approach which uses the first price as the seed, the advanced version initialises the EMA at time $t = N-1$ using the Simple Moving Average of the first $N$ prices:

$$\text{EMA}_{N-1} = \frac{1}{N}\sum_{i=0}^{N-1}p_i$$

This reduces the initialisation bias that occurs when using a single price point as the seed value.

2. **Explicit Warmup Handling**: Signals during the warmup period (before the long EMA has enough data) are explicitly set to 0 (neutral) rather than being emitted with unreliable values.

3. **Default Periods**: Uses 12/26 (matching MACD standard periods) instead of the legacy 20/50.

4. **Signal Encoding**: Outputs numeric signals (+1, -1, 0) as arrays rather than string labels, making them directly usable in position-sizing and backtesting calculations.

**When it works well**: Strong trending markets with sustained directional moves.
**Known weakness**: Whipsaw losses in choppy, range-bound markets where the EMAs cross back and forth rapidly.

#### 4.2.2 Donchian Channel Volatility Breakout

The Donchian Channel is a **volatility breakout system** that tracks the highest high and lowest low over a rolling window:

$$\text{UpperBand}_t = \max(h_{t-N}, \ldots, h_{t-1})$$
$$\text{LowerBand}_t = \min(l_{t-N}, \ldots, l_{t-1})$$

**Key design feature — Lookahead Bias Prevention**: The channel calculation excludes the current bar ($t$). The bands at time $t$ only use data from $[t-N, t-1]$. This is critical for honest backtesting — including the current bar's high/low in the channel would create unrealistic results since you wouldn't know those values at the time of the trading decision.

**Asymmetric Entry/Exit**: The system uses different lookback periods for entry (default 20) and exit (default 10). The shorter exit period creates a tighter trailing stop, allowing the system to lock in profits faster than it takes to initiate positions.

**State Machine Logic**:
- From **Flat**: go Long if close breaks above upper band, go Short if close breaks below lower band
- From **Long**: exit to Flat if close drops below the exit channel (trailing low)
- From **Short**: exit to Flat if close rises above the exit channel (trailing high)

**When it works well**: Markets that experience prolonged breakouts from consolidation ranges.
**Known weakness**: False breakouts — prices briefly pierce the channel then reverse.

---

### 4.3 Module 2: Mean-Reversion & Statistical Arbitrage

These algorithms assume that **prices tend to return to a mean or equilibrium level** and seek to exploit temporary deviations.

#### 4.3.1 Cointegrated Pairs Trading (Z-Score Arbitrage)

This is the most statistically rigorous algorithm in the system. It exploits the tendency of two correlated assets to maintain a stable long-term relationship, even as their individual prices fluctuate.

**Core concept**: If two assets (e.g., Coca-Cola and Pepsi) are cointegrated, their price ratio or spread tends to revert to a mean. When the spread deviates significantly, you go long the underperformer and short the outperformer, expecting convergence.

**Mathematical pipeline:**

1. **Log-Price Transformation**: Prices are log-transformed to ensure percentage-based analysis and to stabilise variance:
$$y = \ln(P_A), \quad x = \ln(P_B)$$

2. **Rolling OLS Hedge Ratio**: Over a 250-bar estimation window, the system computes a rolling hedge ratio $\beta$ via ordinary least squares regression:
$$\beta_t = \frac{\text{Cov}(X, Y)}{\text{Var}(X)}$$

3. **Spread Construction**: The spread is the residual after hedging:
$$S_t = y_t - \beta_t \cdot x_t$$

4. **Z-Score Normalisation**: The spread is normalised over a 30-bar rolling window:
$$Z_t = \frac{S_t - \mu_{S,t}}{\sigma_{S,t}}$$

5. **Signal Generation**:
   - $Z > +2.0$: Spread is overbought → Short A, Long B
   - $Z < -2.0$: Spread is oversold → Long A, Short B
   - $|Z| \leq 0.0$: Close position

**Critical safeguard — ADF Stationarity Test**: Before emitting any signals, the system runs an Augmented Dickey-Fuller test on the spread. If the ADF p-value exceeds 0.05, the spread is deemed non-stationary (meaning the cointegration relationship has broken down), and all signals are halted. This prevents the system from trading on a diverging spread that may never revert.

**When it works well**: Pairs of fundamentally related stocks with stable long-term relationships.
**Known weakness**: Cointegration can break down permanently (e.g., one company undergoes a structural change). The ADF test provides a safety valve but isn't instantaneous.

#### 4.3.2 Bollinger Band Mean-Reversion

Bollinger Bands create a statistical envelope around price based on a rolling mean and standard deviation:

$$\mu_t = \text{SMA}(N), \quad U_t = \mu_t + K\sigma_t, \quad L_t = \mu_t - K\sigma_t$$

With defaults of $N=20$ and $K=2.0$, the bands theoretically contain approximately 95% of price action under a normal distribution.

**State Engine**:
- **Long entry** when price touches or drops below the lower band (statistically oversold)
- **Short entry** when price touches or rises above the upper band (statistically overbought)
- **Exit** when price returns to the middle band (SMA) — capturing the mean reversion

**Implementation note**: The population standard deviation ($1/N$) is used rather than the sample standard deviation ($1/(N-1)$), consistent with the original Bollinger specification.

**When it works well**: Range-bound, choppy markets where prices oscillate around a mean.
**Known weakness**: Strong structural trends — in a sustained rally, prices can "ride the upper band" for extended periods, generating false short signals.

---

### 4.4 Module 3: Econometrics & Machine Learning

These algorithms apply more sophisticated statistical and machine learning techniques to extract predictive signals from price data.

#### 4.4.1 ARIMA-GARCH Volatility-Adjusted Return Model

This is a two-stage econometric model that separately forecasts **expected returns** (ARIMA) and **expected volatility** (GARCH), then combines them for volatility-adjusted position sizing.

**Stage 1 — ARIMA Conditional Mean:**

ARIMA (AutoRegressive Integrated Moving Average) models the expected return as a function of past returns and past forecast errors:

$$r_t = \mu + \sum_{i=1}^{p}\phi_i r_{t-i} + \sum_{j=1}^{q}\theta_j \epsilon_{t-j} + \epsilon_t$$

The default configuration uses ARIMA(1,0,1) — one autoregressive term, zero differencing (returns are already stationary), and one moving average term. Parameters are estimated via Maximum Likelihood Estimation (MLE) over a trailing 500-bar window.

**Stage 2 — GARCH Conditional Variance:**

GARCH models the variance of the ARIMA residuals as a function of past squared residuals and past variances:

$$\sigma_t^2 = \omega + \alpha_1 \epsilon_{t-1}^2 + \beta_1 \sigma_{t-1}^2$$

This captures **volatility clustering** — the empirical observation that large price moves tend to be followed by large price moves, and small by small.

**Stage 3 — Position Sizing:**

The forecast return is divided by the forecast variance, scaled by a risk aversion parameter:

$$\text{position\_size} = \frac{\hat{r}_{t+1}}{\lambda \cdot \hat{\sigma}_{t+1}^2}$$

This is derived from the **Kelly Criterion** / mean-variance optimisation framework. In high-volatility regimes, position sizes shrink automatically. The result is capped at ±2.0× leverage to prevent extreme allocations.

**Fallback mechanism**: If MLE fails to converge (which can happen with short or unusual data series), the system falls back to historical mean return and exponentially-weighted variance. The `converged` flag in the output tells the caller whether the full model was used.

**When it works well**: Liquid markets with sufficient history and stable statistical properties.
**Known weakness**: Financial returns often violate the normality assumptions underlying these models. The GARCH model is particularly sensitive to extreme outliers.

#### 4.4.2 Random Forest Classifier

This is a non-parametric machine learning approach that makes no assumptions about the distribution of returns. It trains a Random Forest ensemble on five features derived strictly from OHLCV data:

| Feature | Formula | Intuition |
|---------|---------|-----------|
| 1-bar log return | $\ln(p_t / p_{t-1})$ | Recent momentum |
| k-bar log return | $\ln(p_t / p_{t-k})$ | Medium-term momentum |
| Normalised range | $(h_t - l_t) / p_t$ | Intrabar volatility |
| Volume ratio | $v_t / \text{Mean}(v_{t-20..t})$ | Volume anomaly |
| Price Z-score | $(p_t - \mu_{20}) / \sigma_{20}$ | Relative price level |

**Target**: Binary classification — will the price be higher ($+1$) or lower ($-1$) in $k=5$ bars?

**Anti-overfitting measures**:
1. **Strict rolling window**: The model is trained only on the trailing 1000 bars. Feature scaling (StandardScaler) is fit exclusively on the training window — never on future data.
2. **Balanced class weights**: Compensates for potential class imbalance in the training labels.
3. **Confidence threshold** ($\tau = 0.60$): Only emit a signal when the model's probability exceeds 60% (Long) or is below 40% (Short). Between 40–60%, the signal is neutral — the model isn't confident enough.

**When it works well**: Markets with detectable non-linear patterns in OHLCV data.
**Known weakness**: Overfitting to historical noise, especially with small or non-representative training windows. The model provides no economic rationale for its predictions.

---

### 4.5 Algorithm Summary Matrix

| Algorithm | Category | Paradigm | Input Data | Key Guardrail | Status |
|-----------|----------|----------|------------|---------------|--------|
| **EMA/RSI (Legacy)** | Composite | Trend + Momentum | Close | Min 64 bars | ✅ Pipeline-integrated |
| **Dual EMA Crossover** | Momentum | Trend-Following | Close | Short < Long validation | 🔧 Standalone toolkit |
| **Donchian Breakout** | Momentum | Volatility Breakout | High, Low, Close | Lookahead bias prevention | 🔧 Standalone toolkit |
| **Pairs Trading** | Mean-Reversion | Statistical Arbitrage | Close (×2 assets) | ADF stationarity test | 🔧 Standalone toolkit |
| **Bollinger Bands** | Mean-Reversion | Local Gaussian Reversion | Close | Zero-variance guard | 🔧 Standalone toolkit |
| **ARIMA-GARCH** | Econometrics | Volatility-Adjusted | Close | MLE fallback + leverage cap | 🔧 Standalone toolkit |
| **Random Forest** | Machine Learning | Non-linear Classification | OHLCV | Rolling-window scaling | 🔧 Standalone toolkit |

> **Note on inconsistencies identified during documentation**: 
> - The legacy EMA uses `ewm(adjust=False)` with the first price as the implicit seed, while the advanced `DualEMACrossover` class uses explicit SMA-seeded initialisation. Both are valid approaches, but they will produce slightly different EMA values for the same data. If the advanced algorithms are eventually integrated into the pipeline, this difference should be reconciled.
> - The legacy signal uses string labels (`"BUY"`, `"SELL"`, `"HOLD"`) while the advanced algorithms use integer signals (`+1`, `-1`, `0`). A signal normalisation layer would be needed for integration.
> - The `DualEMACrossover` defaults to 12/26 periods, while the legacy pipeline uses 20/50. These serve different trading horizons and would produce different signals on the same data.

---

## 5. P&L Accounting Methodology

### Why FIFO?

MacroScope uses **FIFO (First-In, First-Out)** matching for profit and loss calculation. When shares are sold, they are matched against the oldest unsold BUY lots first. The three common accounting methods and why FIFO was chosen:

| Method | Rule | Trade-off |
|--------|------|-----------|
| **FIFO** (chosen) | Match sells against oldest buys first | Most widely accepted; matches natural chronological order; required by many tax jurisdictions |
| **LIFO** (Last-In, First-Out) | Match sells against newest buys first | Can defer taxable gains but is banned in some jurisdictions (e.g., IFRS) |
| **Average Cost** | Sells reduce the position at the weighted-average cost | Simplest, but loses individual lot tracking |

FIFO was chosen because it aligns with how most brokers report trades and how most tax authorities expect gains to be calculated. It also provides the most granular tracking — each individual purchase lot is preserved until matched.

### Fee Allocation

Fees are allocated to affect the effective per-share economics of each trade:

- **Buy-side fees**: Increase the cost basis per share
  $$\text{cost\_per\_share} = \text{execution\_price} + \frac{\text{fee}}{\text{quantity}}$$

- **Sell-side fees**: Decrease the net proceeds per share
  $$\text{proceeds\_per\_share} = \text{execution\_price} - \frac{\text{fee}}{\text{quantity}}$$

This means fees are fully reflected in the realised P&L of each matched lot, rather than being tracked as a separate line item.

### Realised vs. Unrealised P&L

- **Realised P&L**: Calculated when a SELL order is matched against BUY lots:
  $$\text{realised\_pnl} = \text{matched\_qty} \times (\text{proceeds\_per\_share} - \text{cost\_per\_share})$$

- **Unrealised P&L**: For open (unmatched) BUY lots, the current market price (most recent close from `price_data`) is used for mark-to-market valuation:
  $$\text{unrealised\_pnl} = \text{market\_value} - \text{total\_invested}$$
  where $\text{market\_value} = \text{open\_qty} \times \text{current\_price}$ and $\text{total\_invested} = \text{open\_qty} \times \text{avg\_cost}$.

- **Total P&L**: The sum of realised and unrealised, giving a complete picture of portfolio performance.

### FIFO Matching Example

Suppose three trades in AAPL:

| Order | Side | Qty | Price | Fee |
|-------|------|-----|-------|-----|
| #1 | BUY | 10 | $150.00 | $1.00 |
| #2 | BUY | 5 | $160.00 | $0.50 |
| #3 | SELL | 12 | $170.00 | $1.20 |

**FIFO matching for the SELL of 12 shares:**

1. Match against Lot #1 (10 shares):
   - Cost per share: $150.00 + ($1.00 / 10) = **$150.10**
   - Proceeds per share: $170.00 - ($1.20 / 12) = **$169.90**
   - Realised P&L: 10 × ($169.90 - $150.10) = **+$198.00**

2. Match against Lot #2 (2 of 5 shares):
   - Cost per share: $160.00 + ($0.50 / 5) = **$160.10**
   - Proceeds per share: **$169.90** (same)
   - Realised P&L: 2 × ($169.90 - $160.10) = **+$19.60**

**Remaining open lot**: 3 shares of Lot #2 at $160.10/share
**Total realised P&L**: $198.00 + $19.60 = **$217.60**

---

## 6. Overall Project Structure

```
FredProject/
├── macroscope.db              ← SQLite database (all persistent state)
├── yfin.ipynb                 ← Prototyping notebook
├── quantitative-trading-      ← Formal algorithm specification
│   algorithms-spec.md
├── macroscope_design.json     ← Original design document
├── pyproject.toml
├── requirements.txt
├── .env                       ← FRED API key (legacy)
├── docs/                      ← Project documentation
│   ├── THEORETICAL.md         ← This file
│   └── TECHNICAL.md           ← Technical documentation
├── data/                      ← Reserved for future exports
├── src/
│   ├── db.py                  ← Shared database layer
│   ├── watchlist.py           ← Stock watchlist management
│   ├── price_data.py          ← Hourly price ingestion
│   ├── financials.py          ← Fundamental data snapshots
│   ├── quant.py               ← Signal algorithms (legacy + advanced)
│   ├── output.py              ← Console report formatter
│   ├── trades.py              ← Order ledger + FIFO P&L
│   ├── integration.py         ← Pipeline orchestrator
│   └── _old/                  ← Archived FRED/Streamlit files
└── tests/                     ← Unit tests
```

The pipeline runs in five sequential steps:

1. **Schema initialisation** (`db.init_all_tables()`)
2. **Price data download** (`price_data.update_all()`)
3. **Fundamental snapshots** (`financials.update_all()`)
4. **Signal computation** (`quant.analyse_watchlist()`)
5. **Report generation** (`output.print_report()`)

Trade recording and P&L calculation operate as a separate, parallel subsystem — orders are recorded manually, and the P&L engine reads from both the `executed_orders` table and the `price_data` table (for mark-to-market).

---

## 7. Vision & Roadmap

MacroScope is designed as a modular platform where each new capability plugs into the existing pipeline architecture. The planned evolution:

### Phase 1: Fundamental Analysis (DCF & Valuation Models)
Build on the existing `financials.py` data to compute intrinsic value estimates using Discounted Cash Flow models, comparable company analysis, and balance sheet health scores. The fundamental data infrastructure (53 metrics per stock per day) is already in place — this phase adds the analytical layer on top.

**Architectural fit**: New module (e.g., `src/valuation.py`) consuming `financials.load_history()` data and outputting a fair-value estimate alongside the current technical signals.

### Phase 2: Advanced Algorithm Integration
Wire the six standalone algorithm classes into the automated pipeline, likely through a **signal aggregation framework** that weights and combines signals from multiple algorithms into a single composite recommendation. This would replace or complement the simple EMA/RSI signal.

**Architectural fit**: A new `signal_aggregator.py` module that calls each algorithm class, normalises their outputs to a common format, and produces a weighted consensus signal.

### Phase 3: Sentiment Analysis
Ingest and analyse text data from financial forums (Reddit r/wallstreetbets, r/investing), news APIs, and social media to generate sentiment scores per ticker. Natural language processing or LLM-based analysis would classify sentiment as bullish/bearish/neutral.

**Architectural fit**: New data source module (e.g., `src/sentiment.py`) with its own DB table and `update_all()` function, following the same pattern as `price_data.py` and `financials.py`.

### Phase 4: AI-Powered Research & Correlation Discovery
Use AI models to automatically identify correlations between owned stocks and potential new investment opportunities. This could include sector rotation analysis, factor exposure assessment, and automated screening of the broader market.

**Architectural fit**: A research module that reads the existing watchlist and portfolio data, then queries external data sources and AI models to generate structured investment recommendations.

### Phase 5: Hedging, Asset Management & Risk Management
Implement portfolio-level risk metrics (VaR, Sharpe ratio, maximum drawdown, beta exposure) and suggest hedging strategies. The pairs trading algorithm already lays groundwork for market-neutral positioning.

**Architectural fit**: A `risk.py` module that reads the full portfolio from `trades.pnl_all()`, computes risk metrics, and suggests rebalancing actions.

### Phase 6: Broker Integration
Connect to a broker API (e.g., Interactive Brokers, Alpaca) for programmatic order execution. The `trades.py` module already defines the order data model — this phase adds a bridge from signal generation to actual order placement and fills the `executed_orders` table automatically.

**Architectural fit**: A `broker.py` module that wraps the broker SDK, translates MacroScope signals into API orders, and calls `trades.record_order()` with the execution confirmations.

---

*This document describes the conceptual foundations and strategic direction of MacroScope. For implementation details, database schemas, code walkthroughs, and usage examples, see [TECHNICAL.md](./TECHNICAL.md).*
