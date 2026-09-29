# Quantitative Trading Algorithms Technical Specification

This document provides a language-independent technical specification for implementing six core quantitative trading algorithms. It is designed as an architectural and algorithmic instruction manual for IDE code generators, AI software engineers, and quantitative developers.

---

## System Architectural Principles

All implementations should adhere to the following design constraints:
1. **Stateless Signal Evaluation / State-Managed Warmup**: Algorithms must handle warm-up lookback windows explicitly before emitting actionable trade signals.
2. **Language Independence**: Data structures are defined using abstract typing (`Array`, `Float`, `Int`, `Boolean`, `Map/Dict`).
3. **Immutability & Vector-to-Stream Compatibility**: Algorithms should support both batch backtesting (vectorized time-series operations) and real-time event-driven bar execution.
4. **Strict Input Requirements**: Only OHLCV (Open, High, Low, Close, Volume) market price data and time-series arrays are consumed.

---

## Module 1: Trend-Following & Momentum Algorithms

### 1.1 Dual Exponential Moving Average (EMA) Crossover

#### Overview
Detects directional market trends by calculating the divergence and crossover of a short-term and a long-term exponential moving average.

#### Data Contracts
- **Inputs**:
  - `close_prices`: Ordered array of floating-point closing prices $P = [p_0, p_1, \dots, p_t]$.
- **Parameters**:
  - `short_period` ($N_{\text{short}}$): Integer lookback for short EMA (Default: 12).
  - `long_period` ($N_{\text{long}}$): Integer lookback for long EMA (Default: 26).
- **Outputs**:
  - `signal`: Directional position indicator $\in \{+1 \text{ (Long)}, -1 \text{ (Short)}, 0 \text{ (Neutral/Warmup)}\}$.
  - `ema_short`: Float array of calculated short EMA values.
  - `ema_long`: Float array of calculated long EMA values.

#### Mathematical Logic & Computation Steps
1. **Smoothing Factor Calculation**:
   $$\alpha = \frac{2}{N + 1}$$
2. **Initial Seed**:
   Initialize EMA at time $t = N - 1$ using the simple moving average (SMA) over the first $N$ prices:
   $$\text{EMA}_{N-1}(N) = \frac{1}{N} \sum_{i=0}^{N-1} p_i$$
3. **Recursive Computation** (for $t \ge N$):
   $$\text{EMA}_t(N) = \alpha \cdot p_t + (1 - \alpha) \cdot \text{EMA}_{t-1}(N)$$
4. **Signal Generation Logic**:
   - For $t < N_{\text{long}} - 1$: Output `signal = 0` (Warmup state).
   - For $t \ge N_{\text{long}} - 1$:
     $$\text{signal}_t = \begin{cases} +1 & \text{if } \text{EMA}_t(N_{\text{short}}) > \text{EMA}_t(N_{\text{long}}) \\ -1 & \text{if } \text{EMA}_t(N_{\text{short}}) < \text{EMA}_t(N_{\text{long}}) \\ \text{signal}_{t-1} & \text{if } \text{EMA}_t(N_{\text{short}}) == \text{EMA}_t(N_{\text{long}}) \end{cases}$$

#### Edge Cases & Validation Rules
- **Warmup Check**: Reject execution if array length $|P| < N_{\text{long}}$.
- **Parameter Validation**: Require $N_{\text{short}} < N_{\text{long}}$.
- **Missing Data**: Forward-fill missing price points before calculation; throw exception if initial $N$ bars contain `NaN`.

---

### 1.2 Donchian Channel Volatility-Breakout

#### Overview
Identifies high-volatility price breakout regimes by tracking rolling $N$-bar high and low price channels with independent entry and trailing exit rules.

#### Data Contracts
- **Inputs**:
  - `high_prices`: Array of high prices $H = [h_0, h_1, \dots, h_t]$.
  - `low_prices`: Array of low prices $L = [l_0, l_1, \dots, l_t]$.
  - `close_prices`: Array of close prices $P = [p_0, p_1, \dots, p_t]$.
- **Parameters**:
  - `entry_period` ($N_{\text{entry}}$): Lookback for breakout upper/lower bounds (Default: 20).
  - `exit_period` ($N_{\text{exit}}$): Lookback for trailing channel exit (Default: 10).
- **Outputs**:
  - `signal`: Trading target $\in \{+1 \text{ (Long)}, -1 \text{ (Short)}, 0 \text{ (Flat)}\}$.
  - `upper_channel`: Float array of upper channel values.
  - `lower_channel`: Float array of lower channel values.

#### Mathematical Logic & Computation Steps
1. **Channel Calculation** (Shifted by 1 bar to prevent lookahead bias):
   $$\text{UpperBand}_t = \max(h_{t-N_{\text{entry}}}, \dots, h_{t-1})$$
   $$\text{LowerBand}_t = \min(l_{t-N_{\text{entry}}}, \dots, l_{t-1})$$
   $$\text{ExitLongBand}_t = \min(l_{t-N_{\text{exit}}}, \dots, l_{t-1})$$
   $$\text{ExitShortBand}_t = \max(h_{t-N_{\text{exit}}}, \dots, h_{t-1})$$
2. **Signal State Machine**:
   - Maintain persistent state `current_position` $\in \{+1, -1, 0\}$.
   - Evaluate at bar $t$:
     - If `current_position == 0`:
       - If $p_t > \text{UpperBand}_t \implies \text{Long Entry} (+1)$.
       - If $p_t < \text{LowerBand}_t \implies \text{Short Entry} (-1)$.
     - If `current_position == +1`:
       - If $p_t < \text{ExitLongBand}_t \implies \text{Exit to Flat} (0)$.
     - If `current_position == -1`:
       - If $p_t > \text{ExitShortBand}_t \implies \text{Exit to Flat} (0)$.

#### Edge Cases & Validation Rules
- **Lookahead Bias Prevention**: Never include current bar high $h_t$ or low $l_t$ in channel calculation for current bar signal evaluation.
- **Minimum Data Length**: Array length must be $\ge \max(N_{\text{entry}}, N_{\text{exit}}) + 1$.

---

## Module 2: Mean-Reversion & Statistical Arbitrage

### 2.1 Cointegrated Pairs Trading (Distance / Z-Score Arbitrage)

#### Overview
Exploits mean-reversion in a stationary linear combination of two co-integrated financial assets. Calculates a rolling hedge ratio and Z-score spread to execute statistical arbitrage.

#### Data Contracts
- **Inputs**:
  - `prices_A`: Array of log prices for Asset A, $Y = \ln(P_A)$.
  - `prices_B`: Array of log prices for Asset B, $X = \ln(P_B)$.
- **Parameters**:
  - `estimation_window` ($T$): Estimation window for OLS regression / cointegration (e.g., 250 bars).
  - `z_window` ($M$): Rolling window for Z-score normalization (e.g., 30 bars).
  - `entry_threshold` ($Z_{\text{entry}}$): Positive float for entry signal (Default: 2.0).
  - `exit_threshold` ($Z_{\text{exit}}$): Non-negative float for mean-reversion target (Default: 0.0).
- **Outputs**:
  - `spread`: Calculated spread array.
  - `z_score`: Normalized Z-score array.
  - `weight_A`: Position weight for Asset A.
  - `weight_B`: Position weight for Asset B.

#### Mathematical Logic & Computation Steps
1. **Rolling Ordinary Least Squares (OLS) Regression**:
   Estimate hedge ratio $\beta_t$ over estimation window $[t-T+1, t]$:
   $$\beta_t = \frac{\text{Cov}(X, Y)}{\text{Var}(X)} = \frac{\sum_{i=0}^{T-1} (x_{t-i} - \bar{x})(y_{t-i} - \bar{y})}{\sum_{i=0}^{T-1} (x_{t-i} - \bar{x})^2}$$
2. **Spread Calculation**:
   $$S_t = y_t - \beta_t \cdot x_t$$
3. **Rolling Normalization (Z-Score)**:
   $$\mu_{S, t} = \frac{1}{M} \sum_{j=0}^{M-1} S_{t-j}$$
   $$\sigma_{S, t} = \sqrt{\frac{1}{M-1} \sum_{j=0}^{M-1} (S_{t-j} - \mu_{S, t})^2}$$
   $$Z_t = \frac{S_t - \mu_{S, t}}{\sigma_{S, t}}$$
4. **Execution Logic**:
   - If $Z_t > +Z_{\text{entry}}$: Spread is overbought $\implies$ Short Asset A, Long Asset B ($\text{weight}_A = -1.0, \text{weight}_B = +\beta_t$).
   - If $Z_t < -Z_{\text{entry}}$: Spread is oversold $\implies$ Long Asset A, Short Asset B ($\text{weight}_A = +1.0, \text{weight}_B = -\beta_t$).
   - If $|Z_t| \le Z_{\text{exit}}$: Close position ($\text{weight}_A = 0.0, \text{weight}_B = 0.0$).

#### Edge Cases & Validation Rules
- **Stationarity Verification**: Implement an Augmented Dickey-Fuller (ADF) test check on $S_t$; halt signal emission if ADF $p$-value $> 0.05$.
- **Zero Variance Guard**: Check $\sigma_{S, t} > 10^{-8}$ before division to prevent division-by-zero runtime panic.

---

### 2.2 Bollinger Band Volatility Mean-Reversion

#### Overview
Identifies localized statistical overbought and oversold price levels assuming local Gaussian distribution over rolling sample windows.

#### Data Contracts
- **Inputs**:
  - `close_prices`: Array of close prices $P = [p_0, p_1, \dots, p_t]$.
- **Parameters**:
  - `period` ($N$): Rolling mean and standard deviation window (Default: 20).
  - `num_std` ($K$): Standard deviation multiplier (Default: 2.0).
- **Outputs**:
  - `middle_band`: Rolling simple moving average $\mu_t$.
  - `upper_band`: Upper Bollinger boundary $U_t$.
  - `lower_band`: Lower Bollinger boundary $L_t$.
  - `signal`: Trading direction $\in \{+1 \text{ (Long)}, -1 \text{ (Short)}, 0 \text{ (Flat)}\}$.

#### Mathematical Logic & Computation Steps
1. **Rolling Mean & Standard Deviation**:
   $$\mu_t = \frac{1}{N} \sum_{i=0}^{N-1} p_{t-i}$$
   $$\sigma_t = \sqrt{\frac{1}{N} \sum_{i=0}^{N-1} (p_{t-i} - \mu_t)^2}$$
2. **Band Construction**:
   $$U_t = \mu_t + K \cdot \sigma_t$$
   $$L_t = \mu_t - K \cdot \sigma_t$$
3. **State Engine**:
   - Long Entry: $p_t \le L_t \implies \text{signal} = +1$.
   - Short Entry: $p_t \ge U_t \implies \text{signal} = -1$.
   - Exit Rule: If active long and $p_t \ge \mu_t \implies \text{signal} = 0$. If active short and $p_t \le \mu_t \implies \text{signal} = 0$.

#### Edge Cases & Validation Rules
- **Constant Price Series**: Handle flat price regimes where $\sigma_t = 0$ by setting $U_t = L_t = \mu_t$.

---

## Module 3: Statistical Econometrics & Machine Learning

### 3.1 ARIMA-GARCH Volatility-Adjusted Return Model

#### Overview
Combines an Autoregressive Integrated Moving Average (ARIMA) model for expected conditional mean returns with a Generalized Autoregressive Conditional Heteroskedasticity (GARCH) model for dynamic volatility estimation. Position sizes are dynamically volatility-adjusted.

#### Data Contracts
- **Inputs**:
  - `close_prices`: Array of close prices $P = [p_0, p_1, \dots, p_t]$.
- **Parameters**:
  - `arima_order`: Tuple $(p, d, q)$ for ARIMA order configuration.
  - `garch_order`: Tuple $(r, s)$ for GARCH conditional variance configuration.
  - `fit_window`: Rolling lookback for model re-fitting (e.g., 500 bars).
  - `risk_aversion`: Scaling factor $\lambda > 0$ for position sizing.
- **Outputs**:
  - `forecast_return` ($\hat{r}_{t+1}$): Projected 1-step mean return.
  - `forecast_volatility` ($\hat{\sigma}_{t+1}$): Projected 1-step conditional standard deviation.
  - `target_position_size`: Continuous real number indicating target leverage/size.

#### Mathematical Logic & Computation Steps
1. **Log Return Transformation**:
   $$r_t = \ln(p_t) - \ln(p_{t-1})$$
2. **ARIMA(p, d, q) Conditional Mean Model**:
   With $d$-times differenced return series $\Delta^d r_t$:
   $$\Delta^d r_t = \mu + \sum_{i=1}^p \phi_i \Delta^d r_{t-i} + \sum_{j=1}^q \theta_j \epsilon_{t-j} + \epsilon_t$$
   Solve parameters $(\mu, \phi, \theta)$ via Maximum Likelihood Estimation (MLE) over the rolling window. Forecast 1-step ahead expectation $\hat{r}_{t+1} = \mathbb{E}[r_{t+1} \mid \mathcal{F}_t]$.
3. **GARCH(r, s) Conditional Variance Model**:
   Model residual error variance $\sigma_t^2 = \text{Var}(\epsilon_t \mid \mathcal{F}_{t-1})$:
   $$\sigma_t^2 = \omega + \sum_{i=1}^r \alpha_i \epsilon_{t-i}^2 + \sum_{j=1}^s \beta_j \sigma_{t-j}^2$$
   Enforce non-negativity parameters: $\omega > 0, \alpha_i \ge 0, \beta_j \ge 0$, and stationarity constraint $\sum \alpha_i + \sum \beta_j < 1$.
   Forecast 1-step conditional variance $\hat{\sigma}_{t+1}^2$.
4. **Volatility-Adjusted Position Sizing**:
   $$\text{position\_size}_{t+1} = \frac{\hat{r}_{t+1}}{\lambda \cdot \hat{\sigma}_{t+1}^2}$$

#### Edge Cases & Validation Rules
- **Non-Convergence Fallback**: If numerical optimization (MLE) fails to converge within iteration limits, fallback to simple historical return mean $\bar{r}$ and exponential variance calculation.
- **Position Cap**: Enforce upper limit cap $|\text{position\_size}| \le \text{MaxLeverage}$ (e.g., $2.0$).

---

### 3.2 Random Forest Classifier on Price-Derived Features

#### Overview
Applies a non-linear Random Forest Ensemble model trained on a multi-dimensional feature matrix derived strictly from OHLCV market data to predict directional price momentum over horizon $k$.

#### Data Contracts
- **Inputs**:
  - `ohlcv_matrix`: Time-series matrix with columns $[Open, High, Low, Close, Volume]$.
- **Parameters**:
  - `n_trees`: Number of decision trees in forest (Default: 500).
  - `forecast_horizon` ($k$): Number of future bars for prediction target (Default: 5).
  - `classification_threshold` ($\tau$): Probability confidence cutoff (Default: 0.60).
  - `train_window`: Rolling bar count for feature scaling and model training (e.g., 1000 bars).
- **Outputs**:
  - `probability_up`: Continuous float $P(Y_{t+k} = +1) \in [0.0, 1.0]$.
  - `signal`: Position output $\in \{+1 \text{ (Long)}, -1 \text{ (Short)}, 0 \text{ (Neutral)}\}$.

#### Mathematical Logic & Computation Steps
1. **Feature Engineering Engine** (Construct feature vector $X_t$ strictly from prices):
   - **Log Return $1$-bar**: $x_{1, t} = \ln(p_t / p_{t-1})$
   - **Log Return $k$-bar**: $x_{2, t} = \ln(p_t / p_{t-k})$
   - **Normalized Range**: $x_{3, t} = \frac{h_t - l_t}{p_t}$
   - **Normalized Volume Ratio**: $x_{4, t} = \frac{v_t}{\text{Mean}(v_{t-20}, \dots, v_t)}$
   - **Z-Score of Price**: $x_{5, t} = \frac{p_t - \mu_{p, 20}}{\sigma_{p, 20}}$
2. **Target Class Labeling**:
   $$Y_t = \begin{cases} +1 & \text{if } \ln(p_{t+k} / p_t) > 0 \\ -1 & \text{if } \ln(p_{t+k} / p_t) \le 0 \end{cases}$$
3. **Ensemble Prediction Logic**:
   Each tree $b \in [1, B]$ predicts binary output $T_b(X_t) \in \{+1, -1\}$.
   $$P(Y_{t+k} = +1 \mid X_t) = \frac{1}{B} \sum_{b=1}^B \mathbb{I}\left(T_b(X_t) = +1\right)$$
4. **Signal Mapping Rule**:
   $$\text{signal}_t = \begin{cases} +1 & \text{if } P(Y_{t+k} = +1 \mid X_t) \ge \tau \\ -1 & \text{if } P(Y_{t+k} = +1 \mid X_t) \le (1 - \tau) \\ 0 & \text{otherwise} \end{cases}$$

#### Edge Cases & Validation Rules
- **Data Leakage Prohibition**: Feature scaling (e.g. Standardization/MinMax) must strictly fit on $[t - \text{train\_window}, t]$ without standardizing across future data.
- **Class Imbalance**: Ensure feature targets utilize balanced sample weights during tree split optimization.

---

## Complete Algorithm Matrix Summary

| Algorithm | Category | Primary Execution Paradigm | Key Failure Mode / Guardrail |
| :--- | :--- | :--- | :--- |
| **Dual EMA Crossover** | Momentum | Trend-Following | Whip-saw losses in choppy, side-ways markets. Require minimum band gap. |
| **Donchian Breakout** | Momentum | Volatility Breakout | False breakouts. Implement trailing stop offset. |
| **Cointegrated Pairs** | Mean-Reversion | Statistical Arbitrage | Cointegration breakdown. Halt execution if ADF test fails. |
| **Bollinger Bands** | Mean-Reversion | Local Gaussian Reversion | Strong structural trends. Enforce strict exit at mean. |
| **ARIMA-GARCH** | Econometrics / ML | Volatility-Adjusted Alpha | MLE optimizer non-convergence. Fallback to historical volatility. |
| **Random Forest** | Machine Learning | Non-linear Pattern Classification | Overfitting & Lookahead bias. Strict rolling-window feature scaling. |
