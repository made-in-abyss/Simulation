"""
Candle data structure and helper metrics.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from market.trade import Trade


@dataclass
class Candle:
    """
    Represents an aggregated OHLCV candle built strictly from executed trades.

    Attributes:
        index: Sequential candle number.
        open: First execution price in this candle.
        high: Maximum execution price in this candle.
        low: Minimum execution price in this candle.
        close: Last execution price in this candle.
        volume: Total volume traded.
        buy_volume: Total volume initiated by aggressive buyers.
        sell_volume: Total volume initiated by aggressive sellers.
        delta: buy_volume - sell_volume (Order Flow Delta).
        trade_count: Number of trades executed.
        start_tick: Simulation tick when candle opened.
        end_tick: Simulation tick when candle closed.
        volume_at_price: Dictionary mapping price level to volume traded at that level.
    """
    index: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    delta: float = 0.0
    trade_count: int = 0
    start_tick: int = 0
    end_tick: int = 0
    time_str: str = ""
    volume_at_price: Dict[float, float] = field(default_factory=dict)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def is_doji(self) -> bool:
        return abs(self.close - self.open) <= 1e-6

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def candle_range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def vwap(self) -> float:
        if self.volume <= 1e-9:
            return self.close
        total_value = sum(p * v for p, v in self.volume_at_price.items())
        return round(total_value / self.volume, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": round(self.volume, 2),
            "buy_volume": round(self.buy_volume, 2),
            "sell_volume": round(self.sell_volume, 2),
            "delta": round(self.delta, 2),
            "trade_count": self.trade_count,
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "time_str": self.time_str,
            "vwap": self.vwap,
        }

    def __repr__(self) -> str:
        color = "GREEN" if self.is_bullish else ("RED" if self.is_bearish else "DOJI")
        return (
            f"Candle[{self.index:03d} | {color}] "
            f"O:{self.open:.2f} H:{self.high:.2f} L:{self.low:.2f} C:{self.close:.2f} | "
            f"Vol:{self.volume:.1f} (Delta:{self.delta:+.1f}) Trades:{self.trade_count}"
        )
