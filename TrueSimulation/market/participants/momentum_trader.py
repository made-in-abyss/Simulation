"""
Momentum Trader participant.
Reacts to recent directional price action and accelerates moves through aggressive market orders.
"""

from typing import List, Tuple
import numpy as np

from market.order import Order, OrderType, Side
from market.participants.base import Participant
from market.regimes import RegimeProfile


class MomentumTrader(Participant):
    """
    Momentum Trader with dynamic position tracking, trailing stops, and profit-taking pullbacks.

    Key realism enhancements:
    - Enters on directional impulse bursts (breakouts).
    - Tracks accumulated open position, average entry price, and holding duration.
    - Takes profits (+8 to +16 ticks) by sending counter-directional market orders, creating natural pullbacks.
    - Cuts losses on adverse moves (-6 to -8 ticks).
    - Creates authentic multi-wave market structure (Impulse -> Pullback -> Retest -> Continuation).
    """

    def __init__(
        self,
        trader_id: str = "MOMENTUM_POOL",
        lookback: int = 8,
        threshold_ticks: float = 2.0,
        base_size: float = 28.0,
        profit_target_ticks: float = 10.0,
        stop_loss_ticks: float = 7.0,
    ):
        super().__init__(trader_id)
        self.lookback = lookback
        self.threshold_ticks = threshold_ticks
        self.base_size = base_size
        self.profit_target_ticks = profit_target_ticks
        self.stop_loss_ticks = stop_loss_ticks

        # Position tracking
        self.net_position: float = 0.0  # Positive = Long, Negative = Short
        self.avg_entry_price: float = 0.0
        self.entry_tick: int = 0

    def on_trade(self, trade) -> None:
        """Tracks net open position and average entry price."""
        if trade.taker_id == self.trader_id:
            signed_qty = trade.quantity if trade.side == Side.BUY else -trade.quantity
            old_pos = self.net_position
            new_pos = old_pos + signed_qty

            if abs(new_pos) > 1e-4:
                if (old_pos >= 0 and signed_qty > 0) or (old_pos <= 0 and signed_qty < 0):
                    # Increasing position size
                    self.avg_entry_price = (
                        self.avg_entry_price * abs(old_pos) + trade.price * abs(signed_qty)
                    ) / abs(new_pos)
                self.net_position = new_pos
            else:
                self.net_position = 0.0
                self.avg_entry_price = 0.0

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

        current_p = recent_prices[-1]
        tick_size = order_book.tick_size
        cur_oid = order_id_counter

        # 1. EVALUATE PROFIT-TAKING & STOP-LOSS ON EXISTING POSITIONS
        if abs(self.net_position) > 4.0 and self.avg_entry_price > 0:
            is_long = self.net_position > 0
            pnl_ticks = (
                (current_p - self.avg_entry_price) / tick_size
                if is_long
                else (self.avg_entry_price - current_p) / tick_size
            )
            ticks_held = tick - self.entry_tick

            # Profit-Taking: price moved into target or momentum exhausted
            take_profit = pnl_ticks >= self.profit_target_ticks or (
                pnl_ticks >= 5.0 and ticks_held >= 25 and rng.random() < 0.25
            )
            # Stop-Loss: adverse move
            stop_out = pnl_ticks <= -self.stop_loss_ticks

            if take_profit or stop_out:
                # Scale out: close 50% to 100% of position with opposing market order
                close_qty = round(
                    abs(self.net_position) * (1.0 if stop_out else rng.uniform(0.5, 0.9)), 1
                )
                close_qty = max(2.0, close_qty)
                exit_side = Side.SELL if is_long else Side.BUY

                cur_oid += 1
                new_orders.append(
                    Order(
                        order_id=cur_oid,
                        trader_id=self.trader_id,
                        side=exit_side,
                        order_type=OrderType.MARKET,
                        price=None,
                        quantity=close_qty,
                        timestamp=tick,
                    )
                )
                # If scaling out, reduce position expectation
                if close_qty >= abs(self.net_position) * 0.95:
                    self.entry_tick = 0
                return cancels, new_orders

        # 2. EVALUATE NEW MOMENTUM ENTRIES
        prior_p = recent_prices[-self.lookback]
        tick_delta = (current_p - prior_p) / tick_size

        # Modulate by regime momentum sensitivity and directional drift
        effective_momentum = (
            tick_delta + regime_profile.directional_drift * 4.0
        ) * regime_profile.momentum_sensitivity

        abs_mom = abs(effective_momentum)
        if abs_mom >= self.threshold_ticks:
            action_prob = min(0.80, 0.22 + 0.08 * (abs_mom - self.threshold_ticks))
            if rng.random() < action_prob:
                side = Side.BUY if effective_momentum > 0 else Side.SELL

                # Prevent over-leveraging in single direction
                max_pos = 120.0
                if (side == Side.BUY and self.net_position < max_pos) or (
                    side == Side.SELL and self.net_position > -max_pos
                ):
                    size_mult = min(2.0, 1.0 + 0.12 * abs_mom)
                    raw_qty = self.base_size * size_mult * rng.uniform(0.8, 1.25) * regime_profile.volatility_mult
                    order_qty = round(max(5.0, min(50.0, raw_qty)), 1)

                    if abs(self.net_position) < 5.0:
                        self.entry_tick = tick
                        self.avg_entry_price = current_p

                    cur_oid += 1
                    new_orders.append(
                        Order(
                            order_id=cur_oid,
                            trader_id=self.trader_id,
                            side=side,
                            order_type=OrderType.MARKET,
                            price=None,
                            quantity=order_qty,
                            timestamp=tick,
                        )
                    )

        return cancels, new_orders
