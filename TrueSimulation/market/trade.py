"""
Trade execution records produced by the matching engine.
"""

from dataclasses import dataclass
from typing import Dict, Any
from market.order import Side


@dataclass
class Trade:
    """
    Represents an executed transaction between a taker (aggressive order)
    and one or more makers (resting limit orders).

    Attributes:
        trade_id: Unique transaction ID.
        maker_order_id: Resting limit order ID.
        taker_order_id: Aggressive incoming order ID.
        maker_id: Participant ID of the liquidity provider.
        taker_id: Participant ID of the liquidity consumer.
        side: Aggressor side (Side.BUY if taker bought at ask, Side.SELL if taker sold at bid).
        price: Execution price.
        quantity: Transacted quantity.
        timestamp: Simulation tick when execution occurred.
    """
    trade_id: int
    maker_order_id: int
    taker_order_id: int
    maker_id: str
    taker_id: str
    side: Side
    price: float
    quantity: float
    timestamp: int

    @property
    def is_buy_aggressor(self) -> bool:
        """True if the buyer was the taker (crossing the spread to hit asks)."""
        return self.side == Side.BUY

    @property
    def is_sell_aggressor(self) -> bool:
        """True if the seller was the taker (crossing the spread to hit bids)."""
        return self.side == Side.SELL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "maker_order_id": self.maker_order_id,
            "taker_order_id": self.taker_order_id,
            "maker_id": self.maker_id,
            "taker_id": self.taker_id,
            "side": self.side.value,
            "price": self.price,
            "quantity": self.quantity,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        arrow = "BUY  ^" if self.is_buy_aggressor else "SELL v"
        return (
            f"Trade #{self.trade_id} @ t={self.timestamp} | "
            f"{arrow} {self.quantity:.2f} @ {self.price:.2f} "
            f"(Taker: {self.taker_id} -> Maker: {self.maker_id})"
        )
