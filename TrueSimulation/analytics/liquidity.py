"""
Liquidity sweep analysis and post-sweep outcome evaluation.
Determines whether a sweep resulted in an immediate reversal or a momentum continuation.
"""

from typing import List, Dict, Any, Optional
from market.liquidity_pool import LiquidityPool, LiquidityType
from analytics.candle import Candle


class LiquidityDetector:
    """
    Monitors liquidity pools and classifies sweep outcomes as Reversals or Continuations.
    """

    def __init__(self, observation_window_candles: int = 2):
        self.observation_window = observation_window_candles
        self.evaluated_sweeps: List[LiquidityPool] = []

    def evaluate_sweeps(
        self,
        swept_pools: List[LiquidityPool],
        candles: List[Candle],
    ) -> None:
        """
        Inspects swept pools and labels their outcome based on subsequent price action.
        """
        if not candles:
            return

        current_candle_idx = candles[-1].index

        for pool in swept_pools:
            if pool.outcome is not None:
                continue

            # Find candle index where sweep occurred
            # Approximate by matching tick range
            sweep_candle_idx = None
            for c in candles:
                if c.start_tick <= pool.swept_tick <= c.end_tick:
                    sweep_candle_idx = c.index
                    break

            if sweep_candle_idx is None:
                # If during the very latest ticks, wait for candle closure
                continue

            # Need at least observation_window candles past the sweep to evaluate outcome
            if current_candle_idx < sweep_candle_idx + self.observation_window:
                continue

            # Evaluate post-sweep candles
            subsequent = candles[sweep_candle_idx : sweep_candle_idx + self.observation_window + 1]
            latest_close = subsequent[-1].close

            if pool.pool_type == LiquidityType.BSL:
                # BSL was swept above pool.price
                # Reversal if price dropped back below pool.price
                # Continuation if price remained above pool.price
                if latest_close < pool.price:
                    pool.outcome = "reversal"
                else:
                    pool.outcome = "continuation"

            elif pool.pool_type == LiquidityType.SSL:
                # SSL was swept below pool.price
                # Reversal if price recovered back above pool.price
                # Continuation if price stayed below pool.price
                if latest_close > pool.price:
                    pool.outcome = "reversal"
                else:
                    pool.outcome = "continuation"

            self.evaluated_sweeps.append(pool)

    def get_statistics(self, all_swept_pools: List[LiquidityPool]) -> Dict[str, Any]:
        """Summary metrics of all liquidity sweep events."""
        total = len(all_swept_pools)
        bsl_count = sum(1 for p in all_swept_pools if p.pool_type == LiquidityType.BSL)
        ssl_count = sum(1 for p in all_swept_pools if p.pool_type == LiquidityType.SSL)
        reversals = sum(1 for p in all_swept_pools if p.outcome == "reversal")
        continuations = sum(1 for p in all_swept_pools if p.outcome == "continuation")
        pending = sum(1 for p in all_swept_pools if p.outcome is None)

        return {
            "total_sweeps": total,
            "bsl_sweeps": bsl_count,
            "ssl_sweeps": ssl_count,
            "reversal_count": reversals,
            "continuation_count": continuations,
            "pending_count": pending,
            "reversal_rate": round(reversals / (reversals + continuations), 2) if (reversals + continuations) > 0 else 0.0,
        }
