"""
Trade and price statistical analysis engine.
Computes volume distributions, trade metrics, return statistics, drawdown,
and distribution moments (skewness, kurtosis) from simulated market data.
"""

import math
from typing import List, Dict, Any, Optional
import numpy as np

from market.trade import Trade
from analytics.candle import Candle


class StatisticsEngine:
    """
    Computes statistical and distributional metrics across executed trades,
    candles, and market order books.
    """

    @staticmethod
    def compute(
        trades: List[Trade],
        candles: List[Candle],
        spread_history: Optional[List[float]] = None,
        large_trade_multiplier: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Calculates comprehensive summary statistics from trades and candles.
        """
        stats: Dict[str, Any] = {}

        # 1. Trade & Volume Metrics
        total_trades = len(trades)
        stats["total_trades"] = total_trades

        if total_trades == 0:
            stats["total_volume"] = 0.0
            stats["buy_volume"] = 0.0
            stats["sell_volume"] = 0.0
            stats["volume_delta"] = 0.0
            stats["avg_trade_size"] = 0.0
            stats["max_trade_size"] = 0.0
            stats["large_trades_count"] = 0
            stats["large_trade_volume"] = 0.0
        else:
            quantities = np.array([t.quantity for t in trades], dtype=float)
            total_vol = float(np.sum(quantities))
            buy_vol = float(sum(t.quantity for t in trades if t.is_buy_aggressor))
            sell_vol = float(sum(t.quantity for t in trades if t.is_sell_aggressor))
            mean_size = float(np.mean(quantities))
            max_size = float(np.max(quantities))

            large_threshold = mean_size * large_trade_multiplier
            large_trades = [t for t in trades if t.quantity >= large_threshold]

            stats["total_volume"] = round(total_vol, 2)
            stats["buy_volume"] = round(buy_vol, 2)
            stats["sell_volume"] = round(sell_vol, 2)
            stats["volume_delta"] = round(buy_vol - sell_vol, 2)
            stats["avg_trade_size"] = round(mean_size, 2)
            stats["max_trade_size"] = round(max_size, 2)
            stats["large_trades_count"] = len(large_trades)
            stats["large_trade_volume"] = round(sum(t.quantity for t in large_trades), 2)

        # 2. Candle & Return Metrics
        stats["candle_count"] = len(candles)
        if len(candles) >= 2:
            closes = np.array([c.close for c in candles], dtype=float)
            opens = np.array([c.open for c in candles], dtype=float)
            volumes = np.array([c.volume for c in candles], dtype=float)

            # Return calculations
            returns = np.diff(closes) / closes[:-1]
            log_returns = np.diff(np.log(closes))

            total_return = float((closes[-1] - opens[0]) / opens[0]) if opens[0] > 0 else 0.0
            mean_return = float(np.mean(returns))
            std_return = float(np.std(returns)) if len(returns) > 1 else 0.0

            # Annualized volatility assuming e.g. 252 days * 390 1-min intervals = 98280 periods
            annualized_vol = float(std_return * math.sqrt(252 * 390)) if std_return > 0 else 0.0

            # Maximum Drawdown
            cumulative = np.maximum.accumulate(closes)
            drawdowns = (closes - cumulative) / cumulative
            max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

            # Bullish / Bearish counts
            bullish_count = sum(1 for c in candles if c.is_bullish)
            bearish_count = sum(1 for c in candles if c.is_bearish)
            doji_count = sum(1 for c in candles if c.is_doji)
            ratio = (bullish_count / bearish_count) if bearish_count > 0 else (float(bullish_count) if bullish_count > 0 else 1.0)

            # Volume statistics
            avg_candle_vol = float(np.mean(volumes))
            vol_volatility = float(np.std(volumes)) if len(volumes) > 1 else 0.0

            # Distribution moments (skewness and kurtosis of returns)
            skewness = 0.0
            kurtosis = 0.0
            if len(returns) > 3 and std_return > 1e-9:
                normalized = (returns - mean_return) / std_return
                skewness = float(np.mean(normalized ** 3))
                kurtosis = float(np.mean(normalized ** 4) - 3.0)  # Excess kurtosis

            stats["first_price"] = round(float(opens[0]), 2)
            stats["last_price"] = round(float(closes[-1]), 2)
            stats["high_price"] = round(float(np.max([c.high for c in candles])), 2)
            stats["low_price"] = round(float(np.min([c.low for c in candles])), 2)
            stats["total_return_pct"] = round(total_return * 100.0, 2)
            stats["mean_return_pct"] = round(mean_return * 100.0, 4)
            stats["return_std_pct"] = round(std_return * 100.0, 4)
            stats["annualized_vol_pct"] = round(annualized_vol * 100.0, 2)
            stats["max_drawdown_pct"] = round(max_drawdown * 100.0, 2)
            stats["bullish_candles"] = bullish_count
            stats["bearish_candles"] = bearish_count
            stats["doji_candles"] = doji_count
            stats["bull_bear_ratio"] = round(ratio, 2)
            stats["avg_candle_volume"] = round(avg_candle_vol, 2)
            stats["volume_volatility"] = round(vol_volatility, 2)
            stats["return_skewness"] = round(skewness, 3)
            stats["return_kurtosis"] = round(kurtosis, 3)
        else:
            stats["total_return_pct"] = 0.0
            stats["mean_return_pct"] = 0.0
            stats["return_std_pct"] = 0.0
            stats["annualized_vol_pct"] = 0.0
            stats["max_drawdown_pct"] = 0.0
            stats["bullish_candles"] = 0
            stats["bearish_candles"] = 0
            stats["doji_candles"] = 0
            stats["bull_bear_ratio"] = 1.0
            stats["avg_candle_volume"] = 0.0
            stats["volume_volatility"] = 0.0
            stats["return_skewness"] = 0.0
            stats["return_kurtosis"] = 0.0

        # 3. Spread statistics if provided
        if spread_history and len(spread_history) > 0:
            valid_spreads = [s for s in spread_history if s is not None and s >= 0]
            if valid_spreads:
                stats["spread_mean"] = round(float(np.mean(valid_spreads)), 4)
                stats["spread_min"] = round(float(np.min(valid_spreads)), 4)
                stats["spread_max"] = round(float(np.max(valid_spreads)), 4)
                stats["spread_std"] = round(float(np.std(valid_spreads)), 4)
            else:
                stats["spread_mean"] = 0.0
                stats["spread_min"] = 0.0
                stats["spread_max"] = 0.0
                stats["spread_std"] = 0.0
        else:
            stats["spread_mean"] = 0.0
            stats["spread_min"] = 0.0
            stats["spread_max"] = 0.0
            stats["spread_std"] = 0.0

        return stats
