"""
Market Maker participant implementation.
Provides deep, continuous, two-sided resting liquidity with realistic depth scaling,
smooth reservation price tracking, and adaptive volatility spread widening.
"""

from typing import List, Tuple, Optional
import numpy as np

from market.order import Order, OrderType, Side
from market.participants.base import Participant
from market.regimes import RegimeProfile


class MarketMaker(Participant):
    """
    Market Maker providing thick, realistic two-sided liquidity.

    Key improvements for market realism:
    - Deep layered limit orders across 12-18 price levels on each side.
    - Liquidity thickness follows a square-root depth curve (thicker further from the touch).
    - Uses Avellaneda-Stoikov inventory skew so quotes smoothly track mid-price without anchoring.
    - Quotes are strictly bounded to prevent self-crossing and maintain realistic spreads.
    - Quote replenishment is steady and maintains continuous book presence.
    """

    def __init__(
        self,
        trader_id: str = "MM_CORE",
        levels_per_side: int = 15,
        base_size: float = 45.0,
        cancel_distance_ticks: int = 25,
    ):
        super().__init__(trader_id)
        self.levels_per_side = levels_per_side
        self.base_size = base_size
        self.cancel_distance_ticks = cancel_distance_ticks
        self.inventory: float = 0.0
        self.recent_taker_flow: float = 0.0

    def on_trade(self, trade) -> None:
        """Tracks net inventory position from executed maker fills and monitors toxic taker flow."""
        # Inventory update if MM was maker
        if trade.maker_id == self.trader_id:
            if trade.side == Side.BUY:
                self.inventory -= trade.quantity
            else:
                self.inventory += trade.quantity

        # Adverse selection monitor: track aggressive taker flow pressure
        flow = trade.quantity if trade.side == Side.BUY else -trade.quantity
        self.recent_taker_flow = 0.82 * self.recent_taker_flow + 0.18 * flow

    @staticmethod
    def _get_psychological_weight(price: float, rng: np.random.Generator) -> float:
        """
        Calculates realistic liquidity clumping at psychological round numbers
        while leaving occasional organic air pockets at non-round levels.
        """
        cents = int(round((price % 1.0) * 100)) % 100
        if cents == 0:
            return 3.2   # Major whole dollar ($100.00, $101.00)
        elif cents == 50:
            return 2.5   # Half dollar ($100.50)
        elif cents in (25, 75):
            return 1.8   # Quarter levels ($100.25, $100.75)
        elif cents % 10 == 0:
            return 1.35  # Dime levels ($100.10, $100.20...)
        
        # 22% chance of thin air pocket at intermediate levels, allowing rapid FVG formation
        if rng.random() < 0.22:
            return 0.35
        return 0.85

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

        mid = order_book.mid_price
        tick_size = order_book.tick_size

        # Mean-revert / decay accumulated inventory risk position and taker flow
        self.inventory *= 0.96
        self.recent_taker_flow *= 0.90

        # Symmetric reservation price with bounded inventory skew
        inv_skew = float(np.clip(self.inventory * 0.0001, -0.03, 0.03))
        center_price = order_book.round(mid - inv_skew)
        half_spread_ticks = max(1, regime_profile.mm_spread_ticks // 2)

        # Toxic flow defense: if heavy aggressive selling occurs, shade bids down; if heavy buying, shade asks up
        toxic_bid_shade = min(3, int(max(0, -self.recent_taker_flow) // 40))
        toxic_ask_shade = min(3, int(max(0, self.recent_taker_flow) // 40))

        # 1. Cancel quotes that drifted too far from active mid price or periodic churn
        for oid in list(self.active_order_ids):
            if oid in order_book.order_map:
                existing_order, _, _ = order_book.order_map[oid]
                dist_ticks = abs(existing_order.price - mid) / tick_size
                if dist_ticks > self.cancel_distance_ticks or rng.random() < 0.20:
                    cancels.append(oid)
            else:
                cancels.append(oid)

        # 2. Inspect active depth across top levels
        bid_depth = {p: q for p, q in order_book.get_bid_depth(self.levels_per_side + 4)}
        ask_depth = {p: q for p, q in order_book.get_ask_depth(self.levels_per_side + 4)}

        cur_oid = order_id_counter

        # 3. Layer Bids and Asks with psychological weighting & toxic flow offsets
        for i in range(1, self.levels_per_side + 1):
            bid_offset = (half_spread_ticks + toxic_bid_shade + i - 1) * tick_size
            ask_offset = (half_spread_ticks + toxic_ask_shade + i - 1) * tick_size

            bid_price = order_book.round(center_price - bid_offset)
            ask_price = order_book.round(center_price + ask_offset)

            # Ensure strict separation and order integrity
            if bid_price >= ask_price:
                bid_price = order_book.round(center_price - tick_size * i)
                ask_price = order_book.round(center_price + tick_size * i)

            depth_curve = 0.55 + 0.25 * np.sqrt(i)
            base_target = self.base_size * regime_profile.mm_depth_mult * depth_curve

            # Bid side with psychological level weighting
            if bid_price > 0:
                bid_weight = self._get_psychological_weight(bid_price, rng)
                target_b_qty = base_target * bid_weight
                current_b_qty = bid_depth.get(bid_price, 0.0)

                if current_b_qty < target_b_qty * 0.60:
                    replenish_qty = round(target_b_qty * rng.uniform(0.85, 1.25), 1)
                    cur_oid += 1
                    new_orders.append(
                        Order(
                            order_id=cur_oid,
                            trader_id=self.trader_id,
                            side=Side.BUY,
                            order_type=OrderType.LIMIT,
                            price=bid_price,
                            quantity=replenish_qty,
                            timestamp=tick,
                        )
                    )

            # Ask side with psychological level weighting
            ask_weight = self._get_psychological_weight(ask_price, rng)
            target_a_qty = base_target * ask_weight
            current_a_qty = ask_depth.get(ask_price, 0.0)

            if current_a_qty < target_a_qty * 0.60:
                replenish_qty = round(target_a_qty * rng.uniform(0.85, 1.25), 1)
                cur_oid += 1
                new_orders.append(
                    Order(
                        order_id=cur_oid,
                        trader_id=self.trader_id,
                        side=Side.SELL,
                        order_type=OrderType.LIMIT,
                        price=ask_price,
                        quantity=replenish_qty,
                        timestamp=tick,
                    )
                )

        return cancels, new_orders
