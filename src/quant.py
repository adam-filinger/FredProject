"""
quant.py - Quantitative trading algorithms & signal generation.

Implements six core algorithms from the Quantitative Trading Algorithms
Technical Specification, plus the original EMA/RSI watchlist signal
used by the MacroScope pipeline.

Algorithms
----------
Module 1 – Trend-Following & Momentum:
  1.1  DualEMACrossover        – Dual EMA crossover signal
  1.2  DonchianBreakout        – Donchian channel volatility breakout

Module 2 – Mean-Reversion & Statistical Arbitrage:
  2.1  PairsTradingZScore      – Cointegrated pairs trading (Z-score arb)
  2.2  BollingerBands          – Bollinger band mean-reversion

Module 3 – Statistical Econometrics & Machine Learning:
  3.1  ARIMAGARCHModel         – ARIMA-GARCH volatility-adjusted returns
  3.2  RandomForestSignal      – Random Forest classifier on OHLCV features

Legacy / Pipeline API (preserved)
---------------------------------
compute_ema(series, span) -> pd.Series
compute_rsi(series, period=14) -> pd.Series
generate_signal(close) -> dict
analyse_watchlist() -> pd.DataFrame
"""

import warnings
import numpy as np
import pandas as pd
import db
import price_data as pd_module


# ═══════════════════════════════════════════════════════════════════════════
# LEGACY PUBLIC API  (used by integration.py / output.py — do not remove)
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# HELPER: SMA-seeded EMA (spec-compliant)
# ═══════════════════════════════════════════════════════════════════════════

def _ema_sma_seeded(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Compute EMA with SMA seed over the first *period* bars.

    Returns an array the same length as *prices*.
    Values before index (period - 1) are NaN (warmup).
    """
    n = len(prices)
    ema = np.full(n, np.nan)
    if n < period:
        return ema

    # Seed: SMA over first N bars
    ema[period - 1] = np.mean(prices[:period])
    alpha = 2.0 / (period + 1)

    for t in range(period, n):
        ema[t] = alpha * prices[t] + (1 - alpha) * ema[t - 1]

    return ema


# ═══════════════════════════════════════════════════════════════════════════
# 1.1  DUAL EMA CROSSOVER
# ═══════════════════════════════════════════════════════════════════════════

class DualEMACrossover:
    """
    Spec §1.1 – Dual Exponential Moving Average Crossover.

    Detects directional market trends via divergence / crossover of a
    short-term and long-term EMA.

    Parameters
    ----------
    short_period : int  (default 12)
    long_period  : int  (default 26)
    """

    def __init__(self, short_period: int = 12, long_period: int = 26):
        if short_period >= long_period:
            raise ValueError(
                f"short_period ({short_period}) must be < long_period ({long_period})"
            )
        self.short_period = short_period
        self.long_period = long_period

    def run(self, close_prices: pd.Series) -> dict:
        """
        Execute the algorithm on a close price series.

        Returns
        -------
        dict with keys:
            signal     : int array  (+1 Long, -1 Short, 0 Warmup)
            ema_short  : float array
            ema_long   : float array
        """
        prices = close_prices.to_numpy(dtype=float, na_value=np.nan).copy()

        if len(prices) < self.long_period:
            raise ValueError(
                f"Need >= {self.long_period} bars, got {len(prices)}"
            )

        # Forward-fill interior NaNs; reject if first N bars contain NaN
        if np.any(np.isnan(prices[:self.long_period])):
            # try forward-fill
            for i in range(1, len(prices)):
                if np.isnan(prices[i]):
                    prices[i] = prices[i - 1]
            if np.any(np.isnan(prices[:self.long_period])):
                raise ValueError(
                    "Initial long_period bars contain unfillable NaN values"
                )

        ema_short = _ema_sma_seeded(prices, self.short_period)
        ema_long = _ema_sma_seeded(prices, self.long_period)

        n = len(prices)
        signals = np.zeros(n, dtype=int)
        warmup_end = self.long_period - 1

        for t in range(warmup_end, n):
            if ema_short[t] > ema_long[t]:
                signals[t] = 1
            elif ema_short[t] < ema_long[t]:
                signals[t] = -1
            else:
                signals[t] = signals[t - 1] if t > warmup_end else 0

        return {
            "signal": signals,
            "ema_short": ema_short,
            "ema_long": ema_long,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 1.2  DONCHIAN CHANNEL VOLATILITY BREAKOUT
# ═══════════════════════════════════════════════════════════════════════════

class DonchianBreakout:
    """
    Spec §1.2 – Donchian Channel Volatility Breakout.

    Tracks rolling N-bar high/low channels with independent entry and
    trailing exit rules.  Channel calc is shifted by 1 bar to prevent
    lookahead bias.

    Parameters
    ----------
    entry_period : int  (default 20)
    exit_period  : int  (default 10)
    """

    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        self.entry_period = entry_period
        self.exit_period = exit_period

    def run(
        self,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> dict:
        """
        Execute the algorithm.

        Returns
        -------
        dict with keys:
            signal        : int array  (+1 Long, -1 Short, 0 Flat)
            upper_channel : float array  (entry upper band)
            lower_channel : float array  (entry lower band)
        """
        highs = high_prices.to_numpy(dtype=float)
        lows = low_prices.to_numpy(dtype=float)
        closes = close_prices.to_numpy(dtype=float)
        n = len(closes)

        min_bars = max(self.entry_period, self.exit_period) + 1
        if n < min_bars:
            raise ValueError(f"Need >= {min_bars} bars, got {n}")

        upper_entry = np.full(n, np.nan)
        lower_entry = np.full(n, np.nan)
        exit_long = np.full(n, np.nan)
        exit_short = np.full(n, np.nan)
        signals = np.zeros(n, dtype=int)

        # Pre-compute channels (shifted by 1 bar: use bars [t-N, t-1])
        for t in range(self.entry_period, n):
            upper_entry[t] = np.max(highs[t - self.entry_period: t])
            lower_entry[t] = np.min(lows[t - self.entry_period: t])

        for t in range(self.exit_period, n):
            exit_long[t] = np.min(lows[t - self.exit_period: t])
            exit_short[t] = np.max(highs[t - self.exit_period: t])

        # State machine
        start = max(self.entry_period, self.exit_period)
        pos = 0

        for t in range(start, n):
            if pos == 0:
                if closes[t] > upper_entry[t]:
                    pos = 1
                elif closes[t] < lower_entry[t]:
                    pos = -1
            elif pos == 1:
                if closes[t] < exit_long[t]:
                    pos = 0
            elif pos == -1:
                if closes[t] > exit_short[t]:
                    pos = 0
            signals[t] = pos

        return {
            "signal": signals,
            "upper_channel": upper_entry,
            "lower_channel": lower_entry,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 2.1  COINTEGRATED PAIRS TRADING (Z-SCORE ARBITRAGE)
# ═══════════════════════════════════════════════════════════════════════════

class PairsTradingZScore:
    """
    Spec §2.1 – Cointegrated Pairs Trading (Distance / Z-Score Arbitrage).

    Exploits mean-reversion in a stationary linear combination of two
    co-integrated assets via rolling OLS hedge ratio + Z-score spread.

    Parameters
    ----------
    estimation_window : int    (default 250)
    z_window          : int    (default 30)
    entry_threshold   : float  (default 2.0)
    exit_threshold    : float  (default 0.0)
    """

    def __init__(
        self,
        estimation_window: int = 250,
        z_window: int = 30,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.0,
    ):
        self.estimation_window = estimation_window
        self.z_window = z_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def run(
        self,
        prices_a: pd.Series,
        prices_b: pd.Series,
    ) -> dict:
        """
        Execute the algorithm.

        Parameters
        ----------
        prices_a : close prices for Asset A (will be log-transformed)
        prices_b : close prices for Asset B (will be log-transformed)

        Returns
        -------
        dict with keys:
            spread     : float array
            z_score    : float array
            weight_a   : float array  (position weight for A)
            weight_b   : float array  (position weight for B)
            beta       : float array  (rolling hedge ratio)
            adf_pvalue : float        (latest ADF p-value on spread)
        """
        from statsmodels.tsa.stattools import adfuller

        y = np.log(prices_a.to_numpy(dtype=float))  # Asset A (dependent)
        x = np.log(prices_b.to_numpy(dtype=float))  # Asset B (independent)
        n = len(y)
        T = self.estimation_window
        M = self.z_window

        min_bars = T + M
        if n < min_bars:
            raise ValueError(f"Need >= {min_bars} bars, got {n}")

        beta = np.full(n, np.nan)
        spread = np.full(n, np.nan)
        z_score = np.full(n, np.nan)
        weight_a = np.zeros(n)
        weight_b = np.zeros(n)

        # Rolling OLS to compute beta and spread
        for t in range(T - 1, n):
            x_win = x[t - T + 1: t + 1]
            y_win = y[t - T + 1: t + 1]
            x_bar = np.mean(x_win)
            y_bar = np.mean(y_win)
            cov_xy = np.sum((x_win - x_bar) * (y_win - y_bar))
            var_x = np.sum((x_win - x_bar) ** 2)
            beta[t] = cov_xy / var_x if var_x > 1e-12 else 0.0
            spread[t] = y[t] - beta[t] * x[t]

        # Rolling Z-score of spread
        for t in range(T - 1 + M - 1, n):
            s_win = spread[t - M + 1: t + 1]
            mu_s = np.mean(s_win)
            sigma_s = np.std(s_win, ddof=1)
            if sigma_s > 1e-8:
                z_score[t] = (spread[t] - mu_s) / sigma_s
            else:
                z_score[t] = 0.0

        # ADF stationarity test on the valid portion of spread
        valid_spread = spread[~np.isnan(spread)]
        adf_pvalue = 1.0
        if len(valid_spread) >= 20:
            try:
                adf_result = adfuller(
                    valid_spread,
                    maxlag=int(len(valid_spread) ** 0.25),
                    result_object=True,
                )
                adf_pvalue = float(adf_result[1])
            except Exception:
                adf_pvalue = 1.0

        # Signal generation (only emit if spread is stationary)
        start = T - 1 + M - 1
        pos_a = 0.0

        for t in range(start, n):
            if np.isnan(z_score[t]):
                continue

            # Halt signals if ADF test suggests non-stationarity
            if adf_pvalue > 0.05:
                weight_a[t] = 0.0
                weight_b[t] = 0.0
                continue

            z = z_score[t]
            b = beta[t] if not np.isnan(beta[t]) else 0.0

            if z > self.entry_threshold:
                # Spread overbought → short A, long B
                pos_a = -1.0
                weight_a[t] = -1.0
                weight_b[t] = b
            elif z < -self.entry_threshold:
                # Spread oversold → long A, short B
                pos_a = 1.0
                weight_a[t] = 1.0
                weight_b[t] = -b
            elif abs(z) <= self.exit_threshold:
                # Close position
                pos_a = 0.0
                weight_a[t] = 0.0
                weight_b[t] = 0.0
            else:
                # Hold current position
                weight_a[t] = pos_a
                weight_b[t] = -pos_a * b if pos_a != 0 else 0.0

        return {
            "spread": spread,
            "z_score": z_score,
            "weight_a": weight_a,
            "weight_b": weight_b,
            "beta": beta,
            "adf_pvalue": round(adf_pvalue, 6),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 2.2  BOLLINGER BAND VOLATILITY MEAN-REVERSION
# ═══════════════════════════════════════════════════════════════════════════

class BollingerBands:
    """
    Spec §2.2 – Bollinger Band Volatility Mean-Reversion.

    Identifies overbought / oversold levels via rolling SMA ± K·σ bands
    with a state engine for entry/exit.

    Parameters
    ----------
    period  : int    (default 20)
    num_std : float  (default 2.0)
    """

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std

    def run(self, close_prices: pd.Series) -> dict:
        """
        Execute the algorithm.

        Returns
        -------
        dict with keys:
            signal      : int array  (+1 Long, -1 Short, 0 Flat)
            middle_band : float array  (SMA)
            upper_band  : float array
            lower_band  : float array
        """
        prices = close_prices.to_numpy(dtype=float)
        n = len(prices)
        N = self.period
        K = self.num_std

        if n < N:
            raise ValueError(f"Need >= {N} bars, got {n}")

        middle = np.full(n, np.nan)
        upper = np.full(n, np.nan)
        lower = np.full(n, np.nan)
        signals = np.zeros(n, dtype=int)

        for t in range(N - 1, n):
            window = prices[t - N + 1: t + 1]
            mu = np.mean(window)
            # Population std (spec: 1/N not 1/(N-1))
            sigma = np.std(window, ddof=0)
            middle[t] = mu
            upper[t] = mu + K * sigma
            lower[t] = mu - K * sigma

        # State engine
        pos = 0
        for t in range(N - 1, n):
            p = prices[t]

            if pos == 0:
                if p <= lower[t]:
                    pos = 1   # long entry
                elif p >= upper[t]:
                    pos = -1  # short entry
            elif pos == 1:
                if p >= middle[t]:
                    pos = 0   # exit long at mean
            elif pos == -1:
                if p <= middle[t]:
                    pos = 0   # exit short at mean

            signals[t] = pos

        return {
            "signal": signals,
            "middle_band": middle,
            "upper_band": upper,
            "lower_band": lower,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3.1  ARIMA-GARCH VOLATILITY-ADJUSTED RETURN MODEL
# ═══════════════════════════════════════════════════════════════════════════

class ARIMAGARCHModel:
    """
    Spec §3.1 – ARIMA-GARCH Volatility-Adjusted Return Model.

    Combines ARIMA for conditional mean returns with GARCH for dynamic
    volatility estimation.  Position sizes are volatility-adjusted.

    Parameters
    ----------
    arima_order    : tuple (p, d, q)  (default (1, 0, 1))
    garch_order    : tuple (r, s)     (default (1, 1))
    fit_window     : int              (default 500)
    risk_aversion  : float > 0        (default 1.0)
    max_leverage   : float            (default 2.0)
    """

    def __init__(
        self,
        arima_order: tuple = (1, 0, 1),
        garch_order: tuple = (1, 1),
        fit_window: int = 500,
        risk_aversion: float = 1.0,
        max_leverage: float = 2.0,
    ):
        self.arima_order = arima_order
        self.garch_order = garch_order
        self.fit_window = fit_window
        self.risk_aversion = risk_aversion
        self.max_leverage = max_leverage

    def _fallback_forecast(self, returns: np.ndarray) -> tuple:
        """
        Fallback when MLE fails to converge: historical mean return
        and exponentially-weighted variance.
        """
        mean_ret = float(np.mean(returns))
        # Exponential variance with span = len(returns)
        ew_var = float(
            pd.Series(returns).ewm(span=len(returns)).var().iloc[-1]
        )
        vol = np.sqrt(max(ew_var, 1e-12))
        return mean_ret, vol

    def run(self, close_prices: pd.Series) -> dict:
        """
        Execute the algorithm using the trailing fit_window of data.

        Returns
        -------
        dict with keys:
            forecast_return        : float  (1-step ahead expected return)
            forecast_volatility    : float  (1-step ahead conditional σ)
            target_position_size   : float  (vol-adjusted, capped at max_leverage)
            converged              : bool   (True if MLE converged)
        """
        from statsmodels.tsa.arima.model import ARIMA
        from arch import arch_model

        prices = close_prices.to_numpy(dtype=float)
        if len(prices) < self.fit_window + 1:
            raise ValueError(
                f"Need >= {self.fit_window + 1} bars, got {len(prices)}"
            )

        # Use trailing window
        window_prices = prices[-(self.fit_window + 1):]
        log_returns = np.diff(np.log(window_prices))

        converged = True
        forecast_return = 0.0
        forecast_vol = 0.0

        # --- ARIMA conditional mean ---
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                arima = ARIMA(
                    log_returns,
                    order=self.arima_order,
                ).fit(method_kwargs={"maxiter": 200})
                forecast_return = float(arima.forecast(steps=1).iloc[0])
                residuals = arima.resid
        except Exception:
            converged = False
            forecast_return, _ = self._fallback_forecast(log_returns)
            residuals = log_returns - forecast_return

        # --- GARCH conditional variance ---
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Scale residuals to avoid numerical issues (×100)
                scaled_resid = residuals * 100
                garch = arch_model(
                    scaled_resid,
                    vol="Garch",
                    p=self.garch_order[0],
                    q=self.garch_order[1],
                    rescale=False,
                )
                garch_fit = garch.fit(disp="off", show_warning=False)
                # Forecast 1-step variance, then unscale (÷100²)
                fc = garch_fit.forecast(horizon=1)
                forecast_var = float(fc.variance.iloc[-1, 0]) / 10000.0
                forecast_vol = np.sqrt(max(forecast_var, 1e-12))
        except Exception:
            converged = False
            _, forecast_vol = self._fallback_forecast(log_returns)

        # --- Position sizing ---
        if forecast_vol > 1e-12:
            raw_size = forecast_return / (self.risk_aversion * forecast_vol ** 2)
        else:
            raw_size = 0.0

        # Cap at max_leverage
        capped_size = float(np.clip(raw_size, -self.max_leverage, self.max_leverage))

        return {
            "forecast_return": round(forecast_return, 8),
            "forecast_volatility": round(forecast_vol, 8),
            "target_position_size": round(capped_size, 6),
            "converged": converged,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3.2  RANDOM FOREST CLASSIFIER ON PRICE-DERIVED FEATURES
# ═══════════════════════════════════════════════════════════════════════════

class RandomForestSignal:
    """
    Spec §3.2 – Random Forest Classifier on Price-Derived Features.

    Trains a rolling-window RF on five OHLCV-derived features to predict
    directional price momentum over horizon k.

    Parameters
    ----------
    n_trees                  : int    (default 500)
    forecast_horizon         : int    (default 5)
    classification_threshold : float  (default 0.60)
    train_window             : int    (default 1000)
    """

    def __init__(
        self,
        n_trees: int = 500,
        forecast_horizon: int = 5,
        classification_threshold: float = 0.60,
        train_window: int = 1000,
    ):
        self.n_trees = n_trees
        self.k = forecast_horizon
        self.tau = classification_threshold
        self.train_window = train_window

    @staticmethod
    def _build_features(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        k: int,
    ) -> pd.DataFrame:
        """
        Construct the 5-feature matrix strictly from OHLCV data.
        Returns a DataFrame with columns [f1..f5], NaN where warmup is needed.
        """
        n = len(close)
        f1 = np.full(n, np.nan)  # log return 1-bar
        f2 = np.full(n, np.nan)  # log return k-bar
        f3 = np.full(n, np.nan)  # normalized range
        f4 = np.full(n, np.nan)  # normalized volume ratio
        f5 = np.full(n, np.nan)  # z-score of price (20-bar)

        for t in range(1, n):
            f1[t] = np.log(close[t] / close[t - 1])

        for t in range(k, n):
            f2[t] = np.log(close[t] / close[t - k])

        for t in range(n):
            if close[t] > 0:
                f3[t] = (high[t] - low[t]) / close[t]

        # Normalized volume ratio (20-bar rolling mean of volume)
        for t in range(20, n):
            vol_mean = np.mean(volume[t - 20: t + 1])
            if vol_mean > 1e-12:
                f4[t] = volume[t] / vol_mean

        # Z-score of price (20-bar window)
        for t in range(19, n):
            win = close[t - 19: t + 1]
            mu = np.mean(win)
            sigma = np.std(win, ddof=0)
            if sigma > 1e-12:
                f5[t] = (close[t] - mu) / sigma
            else:
                f5[t] = 0.0

        return pd.DataFrame({"f1": f1, "f2": f2, "f3": f3, "f4": f4, "f5": f5})

    def run(self, ohlcv: pd.DataFrame) -> dict:
        """
        Execute the algorithm.

        Parameters
        ----------
        ohlcv : DataFrame with columns [Open, High, Low, Close, Volume]
                (case-insensitive; will be normalised internally)

        Returns
        -------
        dict with keys:
            probability_up : float  (P(Y=+1) at the latest bar)
            signal         : int    (+1 Long, -1 Short, 0 Neutral)
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler

        # Normalise column names to title case
        df = ohlcv.copy()
        df.columns = [c.strip().title() for c in df.columns]
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        open_ = df["Open"].to_numpy(dtype=float)
        high = df["High"].to_numpy(dtype=float)
        low = df["Low"].to_numpy(dtype=float)
        close = df["Close"].to_numpy(dtype=float)
        volume = df["Volume"].to_numpy(dtype=float)
        n = len(close)

        k = self.k
        min_bars = self.train_window + k + 20
        if n < min_bars:
            raise ValueError(f"Need >= {min_bars} bars, got {n}")

        # Build feature matrix
        features = self._build_features(open_, high, low, close, volume, k)

        # Build target labels (no lookahead — only for training rows)
        target = np.full(n, np.nan)
        for t in range(n - k):
            fwd_ret = np.log(close[t + k] / close[t])
            target[t] = 1.0 if fwd_ret > 0 else -1.0

        # Find rows where all features + target are valid
        valid_mask = features.notna().all(axis=1) & ~np.isnan(target)

        # Rolling train: use trailing train_window valid rows ending at t-1
        # to predict at bar t (the latest bar)
        predict_idx = n - 1

        # Ensure the prediction bar has valid features
        if features.iloc[predict_idx].isna().any():
            return {"probability_up": 0.5, "signal": 0}

        # Collect training data: valid rows in [predict_idx - train_window, predict_idx - 1]
        # that have both features and targets
        train_start = max(0, predict_idx - self.train_window)
        train_mask = valid_mask.copy()
        train_mask[:train_start] = False
        train_mask[predict_idx:] = False  # exclude current + future bars

        train_idx = np.where(train_mask)[0]
        if len(train_idx) < 50:
            return {"probability_up": 0.5, "signal": 0}

        X_train = features.iloc[train_idx].to_numpy()
        y_train = target[train_idx]

        # Strict rolling-window feature scaling (no leakage)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_pred = scaler.transform(features.iloc[[predict_idx]].to_numpy())

        # Train Random Forest with balanced class weights
        rf = RandomForestClassifier(
            n_estimators=self.n_trees,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        rf.fit(X_train_scaled, y_train)

        # Predict probability
        proba = rf.predict_proba(X_pred)
        # Find index of class +1
        classes = list(rf.classes_)
        if 1.0 in classes:
            up_idx = classes.index(1.0)
        else:
            up_idx = 0
        prob_up = float(proba[0, up_idx])

        # Signal mapping
        if prob_up >= self.tau:
            signal = 1
        elif prob_up <= (1 - self.tau):
            signal = -1
        else:
            signal = 0

        return {
            "probability_up": round(prob_up, 4),
            "signal": signal,
        }


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE: OHLCV loader for algorithms that need full price bars
# ═══════════════════════════════════════════════════════════════════════════

def fetch_ohlcv(ticker: str, period: str = "730d", interval: str = "1h") -> pd.DataFrame:
    """
    Download OHLCV data from yfinance for a ticker.

    Returns a DataFrame with columns [Open, High, Low, Close, Volume]
    and a UTC-aware DatetimeIndex.

    This is a convenience helper for algorithms that need more than just
    close prices (e.g., DonchianBreakout, RandomForestSignal).
    The data is NOT persisted to the DB — it is returned for direct use.
    """
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period, interval=interval)
    if hist.empty:
        return hist

    hist.index = pd.DatetimeIndex(hist.index).tz_convert("UTC")
    # Keep only OHLCV columns
    ohlcv_cols = ["Open", "High", "Low", "Close", "Volume"]
    available = [c for c in ohlcv_cols if c in hist.columns]
    return hist[available]
