"""
Mean-Reversion Trader participant.
Trades against extreme deviations from rolling equilibrium, stabilizing prices
and facilitating reversals after sharp liquidity sweeps or overextensions.
"""

from typing import List, Tuple
import numpy as np

from market.order import Order, OrderType, Side
from market.participants.base import Participant
from market.regimes import RegimeProfile


class MeanReversionTrader(Participant):
    """
    Mean-Reversion Trader that fades short-term price spikes.
    """

    def __init__(
        self,
        trader_id: str = "MEAN_REV_POOL",
        lookback: int = 20,
        stretch_ticks_threshold: float = 4.0,
        base_size: float = 35.0,
    ):
        super().__init__(trader_id)
        self.lookback = lookback
        self.stretch_ticks = stretch_ticks_threshold
        self.base_size = base_size

    def generate_actions(
        self,
        order_book,
        regime_profile: RegimeProfile,
        rng: np.random.Generator,
        tick: int,
        order_id_counter: int,
        recent_prices: List[float],
    ) -> Tuple[List[int], List[Order]]:
        cancels: List[int] = []
        new_orders: List[Order] = []

        if len(recent_prices) < self.lookback:
            return cancels, new_orders

        # Calculate rolling mean and current stretch
        window = recent_prices[-self.lookback:]
        mean_price = float(np.mean(window))
        current_p = recent_prices[-1]
        deviation_ticks = (current_p - mean_price) / order_book.tick_size

        abs_dev = abs(deviation_ticks)
        if abs_dev >= self.stretch_ticks:
            # Probability scaled by regime mean-reversion strength
            act_prob = min(0.80, 0.20 + 0.08 * (abs_dev - self.stretch_ticks) * regime_profile.mean_reversion_strength)
            if rng.random() < act_prob:
                # Fade the move: if price is too high, SELL; if too low, BUY
                side = Side.SELL if deviation_ticks > 0 else Side.BUY
                raw_qty = self.base_size * min(2.0, 1.0 + 0.1 * abs_dev) * rng.uniform(0.8, 1.25)
                order_qty = round(max(5.0, min(50.0, raw_qty)), 1)

                # 70% market order to fade, 30% near-market limit order
                if rng.random() < 0.70:
                    order = Order(
                        order_id=order_id_counter + 1,
                        trader_id=self.trader_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        price=None,
                        quantity=order_qty,
                        timestamp=tick,
                    )
                else:
                    target_p = order_book.best_ask if side == Side.SELL else order_book.best_bid
                    order = Order(
                        order_id=order_id_counter + 1,
                        trader_id=self.trader_id,
                        side=side,
                        order_type=OrderType.LIMIT,
                        price=target_p or current_p,
                        quantity=order_qty,
                        timestamp=tick,
                    )
                new_orders.append(order)

        return cancels, new_orders
