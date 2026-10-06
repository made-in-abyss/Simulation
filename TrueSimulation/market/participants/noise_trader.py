"""
Noise / Retail Trader participant.
Generates smaller, idiosyncratic, uncoordinated orders creating organic market churn.
"""

from typing import List, Tuple
import numpy as np

from market.order import Order, OrderType, Side
from market.participants.base import Participant
from market.regimes import RegimeProfile


class NoiseTrader(Participant):
    """
    Noise / Retail participant providing organic background volume and stochastic order arrival.
    """

    def __init__(
        self,
        trader_id: str = "NOISE_RETAIL",
        base_size: float = 12.0,
        activity_rate: float = 0.55,
    ):
        super().__init__(trader_id)
        self.base_size = base_size
        self.activity_rate = activity_rate

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

        # Cancel some old resting noise orders
        for oid in list(self.active_order_ids):
            if rng.random() < 0.25:
                cancels.append(oid)

        # Arrival check
        arrival_prob = min(0.95, self.activity_rate * regime_profile.noise_activity)
        if rng.random() > arrival_prob:
            return cancels, new_orders

        # Direction slightly influenced by regime directional drift + random noise
        buy_prob = 0.50 + regime_profile.directional_drift * 0.15
        side = Side.BUY if rng.random() < buy_prob else Side.SELL

        # Multiple micro-orders occasionally generated during active periods
        num_orders = 2 if (rng.random() < 0.25 * regime_profile.volatility_mult) else 1
        cur_oid = order_id_counter

        for _ in range(num_orders):
            cur_oid += 1
            size = round(self.base_size * rng.lognormal(mean=0.0, sigma=0.45), 1)
            size = max(1.0, min(50.0, size))

            # 60% market orders, 40% limit orders near the touch or at round numbers
            if rng.random() < 0.60:
                new_orders.append(
                    Order(
                        order_id=cur_oid,
                        trader_id=self.trader_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        price=None,
                        quantity=size,
                        timestamp=tick,
                    )
                )
            else:
                mid = order_book.mid_price
                ts = order_book.tick_size
                # 35% chance to anchor to nearest psychological round level (.00, .50, .25)
                if rng.random() < 0.35:
                    if side == Side.BUY:
                        # Nearest psychological level below or at mid
                        cand_p = np.floor(mid * 4) / 4.0  # quarter dollar
                        price = order_book.round(min(cand_p, mid - ts))
                    else:
                        cand_p = np.ceil(mid * 4) / 4.0
                        price = order_book.round(max(cand_p, mid + ts))
                else:
                    offset = rng.integers(1, 4) * ts
                    price = order_book.round(mid - offset if side == Side.BUY else mid + offset)

                new_orders.append(
                    Order(
                        order_id=cur_oid,
                        trader_id=self.trader_id,
                        side=side,
                        order_type=OrderType.LIMIT,
                        price=price,
                        quantity=size,
                        timestamp=tick,
                    )
                )

        return cancels, new_orders
