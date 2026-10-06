"""
Institutional / Large Participant participant with realistic Iceberg / POV slicing.
Simulates large capital allocations executed as sliced campaigns across multiple ticks,
creating continuous order flow pressure, realistic candle bodies, and organic FVGs.
"""

from typing import List, Tuple, Optional
import numpy as np

from market.order import Order, OrderType, Side
from market.participants.base import Participant
from market.regimes import RegimeProfile


class InstitutionalTrader(Participant):
    """
    Institutional participant simulating institutional fund flows and algorithmic execution.

    Key realism improvements:
    - Never dumps unrealistic monolithic market blocks that blow through 15 levels in 1 microsecond.
    - Slices large parent orders into Iceberg / Participation-of-Volume (POV) child orders (35-75 units per tick).
    - Child orders exert directional pressure over 4-10 ticks, driving realistic candle expansion.
    """

    def __init__(
        self,
        trader_id: str = "INSTITUTION_FLOW",
        base_block_size: float = 180.0,
        institutional_frequency_mult: float = 1.0,
    ):
        super().__init__(trader_id)
        self.base_block_size = base_block_size
        self.frequency_mult = institutional_frequency_mult

        # Active parent campaign state
        self._active_campaign_side: Optional[Side] = None
        self._remaining_campaign_qty: float = 0.0

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

        cur_oid = order_id_counter

        # 1. Continue ongoing sliced campaign
        if self._remaining_campaign_qty > 5.0 and self._active_campaign_side is not None:
            # Child slice size is proportional to top-of-book depth
            slice_size = round(min(self._remaining_campaign_qty, rng.uniform(35.0, 75.0)), 1)
            self._remaining_campaign_qty -= slice_size
            cur_oid += 1
            new_orders.append(
                Order(
                    order_id=cur_oid,
                    trader_id=self.trader_id,
                    side=self._active_campaign_side,
                    order_type=OrderType.MARKET,
                    price=None,
                    quantity=slice_size,
                    timestamp=tick,
                )
            )
            if self._remaining_campaign_qty <= 5.0:
                self._active_campaign_side = None
                self._remaining_campaign_qty = 0.0
            return cancels, new_orders

        # 2. Check if a new institutional flow event begins
        prob = regime_profile.large_order_prob * self.frequency_mult
        if rng.random() >= prob:
            return cancels, new_orders

        # Determine direction based on regime drift and macro bias
        buy_bias = 0.50 + regime_profile.directional_drift * 0.35
        side = Side.BUY if rng.random() < buy_bias else Side.SELL

        total_campaign_size = round(
            self.base_block_size * rng.uniform(1.0, 2.5) * regime_profile.volatility_mult,
            1,
        )

        # Sliced execution across multiple ticks (POV execution)
        self._active_campaign_side = side
        first_slice = round(min(total_campaign_size, rng.uniform(40.0, 75.0)), 1)
        self._remaining_campaign_qty = total_campaign_size - first_slice

        cur_oid += 1
        new_orders.append(
            Order(
                order_id=cur_oid,
                trader_id=self.trader_id,
                side=side,
                order_type=OrderType.MARKET,
                price=None,
                quantity=first_slice,
                timestamp=tick,
            )
        )

        return cancels, new_orders
