"""
Order definitions and data structures for the Limit Order Book.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Side(str, Enum):
    """Trading side: BUY (bid) or SELL (ask)."""
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self == Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """+1 for BUY, -1 for SELL."""
        return 1 if self == Side.BUY else -1


class OrderType(str, Enum):
    """Order type: LIMIT or MARKET."""
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class Order:
    """
    Represents an order placed by a market participant.

    Attributes:
        order_id: Unique integer identifier.
        trader_id: Identifier of the placing participant.
        side: Side.BUY or Side.SELL.
        order_type: OrderType.LIMIT or OrderType.MARKET.
        price: Price for limit orders (rounded to tick size). None/0.0 for market orders.
        quantity: Total original order size.
        filled_quantity: Accumulated filled amount.
        timestamp: Simulation tick or timestamp when order was created.
    """
    order_id: int
    trader_id: str
    side: Side
    order_type: OrderType
    price: Optional[float]
    quantity: float
    filled_quantity: float = 0.0
    timestamp: int = 0

    @property
    def remaining_quantity(self) -> float:
        """Remaining unfilled quantity."""
        return max(0.0, self.quantity - self.filled_quantity)

    @property
    def is_filled(self) -> bool:
        """True if the order has been completely filled."""
        return self.remaining_quantity <= 1e-9

    def fill(self, fill_qty: float) -> float:
        """
        Record a fill against this order.
        Returns the actual quantity filled.
        """
        actual_fill = min(self.remaining_quantity, fill_qty)
        self.filled_quantity += actual_fill
        return actual_fill
