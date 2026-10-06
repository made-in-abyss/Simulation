"""
Limit Order Book implementation with deterministic price-level queuing.
Supports fast level inspection, depth reporting, cancellations, and spread queries.
"""

import math
from collections import deque
from typing import Dict, List, Optional, Tuple
from sortedcontainers import SortedDict

from market.order import Order, OrderType, Side


def round_price(price: float, tick_size: float = 0.01) -> float:
    """Rounds a price to the nearest tick_size, avoiding floating-point imprecision."""
    decimals = max(0, -int(math.floor(math.log10(tick_size) + 1e-9))) if tick_size < 1 else 0
    return round(round(price / tick_size) * tick_size, decimals)


class PriceLevel:
    """
    A single price level in the order book, maintaining orders in FIFO sequence.
    """
    __slots__ = ("price", "orders", "total_quantity")

    def __init__(self, price: float):
        self.price = price
        self.orders: deque[Order] = deque()
        self.total_quantity: float = 0.0

    def add_order(self, order: Order) -> None:
        self.orders.append(order)
        self.total_quantity += order.remaining_quantity

    def remove_order(self, order: Order) -> bool:
        try:
            self.orders.remove(order)
            self.total_quantity = max(0.0, self.total_quantity - order.remaining_quantity)
            return True
        except ValueError:
            return False

    def deduct_quantity(self, amount: float) -> None:
        self.total_quantity = max(0.0, self.total_quantity - amount)

    @property
    def is_empty(self) -> bool:
        return len(self.orders) == 0 or self.total_quantity <= 1e-9

    def __repr__(self) -> str:
        return f"Level({self.price:.2f}: qty={self.total_quantity:.2f}, orders={len(self.orders)})"


class OrderBook:
    """
    Double-auction Limit Order Book.

    Maintains:
    - Bids sorted ascending by price (best bid is highest price = peekitem(-1))
    - Asks sorted ascending by price (best ask is lowest price = peekitem(0))
    - Order index mapping for O(1) order lookups and fast cancellation
    """

    def __init__(self, initial_price: float = 100.0, tick_size: float = 0.01):
        self.tick_size = tick_size
        self.last_trade_price = round_price(initial_price, tick_size)
        
        # Bids: price -> PriceLevel (highest price is the best bid)
        self.bids: SortedDict[float, PriceLevel] = SortedDict()
        
        # Asks: price -> PriceLevel (lowest price is the best ask)
        self.asks: SortedDict[float, PriceLevel] = SortedDict()
        
        # Fast lookup: order_id -> (Order, PriceLevel, Side)
        self.order_map: Dict[int, Tuple[Order, PriceLevel, Side]] = {}

    def round(self, price: float) -> float:
        """Round price to the book's tick size."""
        return round_price(price, self.tick_size)

    @property
    def best_bid(self) -> Optional[float]:
        """Current highest resting bid price, or None if no bids."""
        if not self.bids:
            return None
        return self.bids.peekitem(-1)[0]

    @property
    def best_ask(self) -> Optional[float]:
        """Current lowest resting ask price, or None if no asks."""
        if not self.asks:
            return None
        return self.asks.peekitem(0)[0]

    @property
    def mid_price(self) -> float:
        """
        Current mid price between best bid and best ask.
        Falls back to best available side or last traded price.
        """
        bb = self.best_bid
        ba = self.best_ask
        if bb is not None and ba is not None:
            return round((bb + ba) / 2.0, 4)
        if bb is not None:
            return bb
        if ba is not None:
            return ba
        return self.last_trade_price

    @property
    def spread(self) -> Optional[float]:
        """Difference between best ask and best bid, or None if book is one-sided."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is not None and ba is not None:
            return round(ba - bb, 4)
        return None

    @property
    def total_bid_volume(self) -> float:
        """Sum of all resting bid quantities."""
        return sum(lvl.total_quantity for lvl in self.bids.values())

    @property
    def total_ask_volume(self) -> float:
        """Sum of all resting ask quantities."""
        return sum(lvl.total_quantity for lvl in self.asks.values())

    @property
    def imbalance(self) -> float:
        """
        Order book imbalance in [-1.0, 1.0].
        Positive values indicate excess buying depth; negative indicate selling depth.
        """
        b_vol = self.total_bid_volume
        a_vol = self.total_ask_volume
        total = b_vol + a_vol
        if total <= 1e-9:
            return 0.0
        return (b_vol - a_vol) / total

    def get_bid_depth(self, levels: int = 10) -> List[Tuple[float, float]]:
        """
        Returns top N bid levels as [(price, quantity), ...], ordered highest price first.
        """
        result = []
        n = len(self.bids)
        for i in range(n - 1, max(-1, n - 1 - levels), -1):
            price, level = self.bids.peekitem(i)
            result.append((price, round(level.total_quantity, 2)))
        return result

    def get_ask_depth(self, levels: int = 10) -> List[Tuple[float, float]]:
        """
        Returns top N ask levels as [(price, quantity), ...], ordered lowest price first.
        """
        result = []
        n = min(levels, len(self.asks))
        for i in range(n):
            price, level = self.asks.peekitem(i)
            result.append((price, round(level.total_quantity, 2)))
        return result

    def get_level_quantity(self, side: Side, price: float) -> float:
        """Returns total resting quantity at a given price level."""
        p = self.round(price)
        book = self.bids if side == Side.BUY else self.asks
        if p in book:
            return book[p].total_quantity
        return 0.0

    def add_limit_order(self, order: Order) -> None:
        """
        Inserts a resting limit order into the book.
        Note: The MatchingEngine must verify that the order does not cross the spread
        before placing it as resting liquidity.
        """
        if order.price is None:
            raise ValueError("Limit orders must specify a price")
        
        price = self.round(order.price)
        order.price = price

        side_dict = self.bids if order.side == Side.BUY else self.asks
        
        if price not in side_dict:
            side_dict[price] = PriceLevel(price)
            
        level = side_dict[price]
        level.add_order(order)
        self.order_map[order.order_id] = (order, level, order.side)

    def cancel_order(self, order_id: int) -> Optional[Order]:
        """
        Cancels an active resting limit order by order_id.
        Removes empty price levels automatically.
        """
        if order_id not in self.order_map:
            return None
            
        order, level, side = self.order_map.pop(order_id)
        level.remove_order(order)
        
        side_dict = self.bids if side == Side.BUY else self.asks
        if level.is_empty:
            side_dict.pop(level.price, None)
            
        return order

    def modify_order_quantity(self, order_id: int, new_quantity: float) -> bool:
        """
        Modifies the quantity of an existing resting order.
        If new_quantity <= filled_quantity, cancels the order.
        """
        if order_id not in self.order_map:
            return False
            
        order, level, side = self.order_map[order_id]
        if new_quantity <= order.filled_quantity + 1e-9:
            self.cancel_order(order_id)
            return True
            
        diff = new_quantity - order.quantity
        order.quantity = new_quantity
        level.total_quantity = max(0.0, level.total_quantity + diff)
        return True

    def remove_empty_levels(self) -> None:
        """Cleans up empty price levels on both sides."""
        for p in list(self.bids.keys()):
            if self.bids[p].is_empty:
                del self.bids[p]
        for p in list(self.asks.keys()):
            if self.asks[p].is_empty:
                del self.asks[p]

    def clear(self) -> None:
        """Wipes all orders and levels from the book."""
        self.bids.clear()
        self.asks.clear()
        self.order_map.clear()
