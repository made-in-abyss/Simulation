"""
Fair Value Gap (FVG) detection, lifecycle tracking, and mitigation analysis.
Implements the 3-candle structural imbalance detector strictly derived from generated price candles.
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from analytics.candle import Candle


class FVGType(str, Enum):
    BULLISH = "bullish"  # Candle 1 High < Candle 3 Low (Demand Imbalance)
    BEARISH = "bearish"  # Candle 1 Low > Candle 3 High (Supply Imbalance)


class FVGStatus(str, Enum):
    ACTIVE = "active"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"


@dataclass
class FairValueGap:
    """
    Represents a Fair Value Gap created across a 3-candle sequence.
    """
    fvg_id: int
    fvg_type: FVGType
    top_price: float
    bottom_price: float
    creation_candle_index: int  # Middle candle index
    candle_1_index: int
    candle_3_index: int
    size: float
    status: FVGStatus = FVGStatus.ACTIVE
    is_touched: bool = False
    touch_candle_index: Optional[int] = None
    fill_percentage: float = 0.0
    filled_candle_index: Optional[int] = None

    def update_lifecycle(self, candle: Candle) -> None:
        """
        Updates gap mitigation (touch / partial fill / full fill) when tested by a subsequent candle.
        """
        if self.status == FVGStatus.FILLED:
            return

        if self.fvg_type == FVGType.BULLISH:
            # Bullish FVG: top_price = Candle 3 Low, bottom_price = Candle 1 High
            if candle.low < self.top_price:
                self.is_touched = True
                if self.touch_candle_index is None:
                    self.touch_candle_index = candle.index

                if candle.low <= self.bottom_price:
                    self.fill_percentage = 100.0
                    self.status = FVGStatus.FILLED
                    self.filled_candle_index = candle.index
                else:
                    penetration = self.top_price - candle.low
                    pct = min(100.0, (penetration / self.size) * 100.0)
                    self.fill_percentage = max(self.fill_percentage, pct)
                    self.status = FVGStatus.PARTIALLY_FILLED

        elif self.fvg_type == FVGType.BEARISH:
            # Bearish FVG: top_price = Candle 1 Low, bottom_price = Candle 3 High
            if candle.high > self.bottom_price:
                self.is_touched = True
                if self.touch_candle_index is None:
                    self.touch_candle_index = candle.index

                if candle.high >= self.top_price:
                    self.fill_percentage = 100.0
                    self.status = FVGStatus.FILLED
                    self.filled_candle_index = candle.index
                else:
                    penetration = candle.high - self.bottom_price
                    pct = min(100.0, (penetration / self.size) * 100.0)
                    self.fill_percentage = max(self.fill_percentage, pct)
                    self.status = FVGStatus.PARTIALLY_FILLED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fvg_id": self.fvg_id,
            "type": self.fvg_type.value,
            "top_price": self.top_price,
            "bottom_price": self.bottom_price,
            "creation_candle_index": self.creation_candle_index,
            "candle_1_index": self.candle_1_index,
            "candle_3_index": self.candle_3_index,
            "size": round(self.size, 2),
            "status": self.status.value,
            "is_touched": self.is_touched,
            "touch_candle_index": self.touch_candle_index,
            "fill_percentage": round(self.fill_percentage, 1),
            "filled_candle_index": self.filled_candle_index,
        }


class FVGDetector:
    """
    Scans sequential candles to identify Fair Value Gaps and tracks their mitigation lifecycle.
    """

    def __init__(self, min_gap_size: float = 0.02):
        self.min_gap_size = min_gap_size
        self.fvgs: List[FairValueGap] = []
        self._fvg_counter = 0
        self._last_checked_idx = 1

    def update(self, candles: List[Candle]) -> None:
        """
        Processes new candles to detect fresh FVGs and updates active ones.
        """
        n = len(candles)
        if n < 3:
            return

        # 1. Detect new FVGs across 3-candle windows [i-1, i, i+1]
        for i in range(self._last_checked_idx, n - 1):
            c1 = candles[i - 1]
            c2 = candles[i]
            c3 = candles[i + 1]

            # Bullish FVG check: c1.high < c3.low
            if c3.low > c1.high + self.min_gap_size:
                self._fvg_counter += 1
                fvg = FairValueGap(
                    fvg_id=self._fvg_counter,
                    fvg_type=FVGType.BULLISH,
                    top_price=round(c3.low, 4),
                    bottom_price=round(c1.high, 4),
                    creation_candle_index=i,
                    candle_1_index=i - 1,
                    candle_3_index=i + 1,
                    size=round(c3.low - c1.high, 4),
                )
                self.fvgs.append(fvg)

            # Bearish FVG check: c1.low > c3.high
            elif c1.low > c3.high + self.min_gap_size:
                self._fvg_counter += 1
                fvg = FairValueGap(
                    fvg_id=self._fvg_counter,
                    fvg_type=FVGType.BEARISH,
                    top_price=round(c1.low, 4),
                    bottom_price=round(c3.high, 4),
                    creation_candle_index=i,
                    candle_1_index=i - 1,
                    candle_3_index=i + 1,
                    size=round(c1.low - c3.high, 4),
                )
                self.fvgs.append(fvg)

        self._last_checked_idx = max(1, n - 2)

        # 2. Update lifecycle of all active and partially filled FVGs against candles following creation
        for fvg in self.fvgs:
            if fvg.status == FVGStatus.FILLED:
                continue
            for k in range(fvg.candle_3_index + 1, n):
                fvg.update_lifecycle(candles[k])
                if fvg.status == FVGStatus.FILLED:
                    break

    @property
    def active_fvgs(self) -> List[FairValueGap]:
        return [f for f in self.fvgs if f.status != FVGStatus.FILLED]

    def get_summary(self) -> Dict[str, Any]:
        total = len(self.fvgs)
        bullish = sum(1 for f in self.fvgs if f.fvg_type == FVGType.BULLISH)
        bearish = sum(1 for f in self.fvgs if f.fvg_type == FVGType.BEARISH)
        filled = sum(1 for f in self.fvgs if f.status == FVGStatus.FILLED)
        partial = sum(1 for f in self.fvgs if f.status == FVGStatus.PARTIALLY_FILLED)
        active = sum(1 for f in self.fvgs if f.status == FVGStatus.ACTIVE)
        touched = sum(1 for f in self.fvgs if f.is_touched)

        avg_size = round(sum(f.size for f in self.fvgs) / total, 3) if total > 0 else 0.0

        return {
            "total_fvgs": total,
            "bullish_fvgs": bullish,
            "bearish_fvgs": bearish,
            "active_fvgs": active,
            "partially_filled_fvgs": partial,
            "filled_fvgs": filled,
            "touched_fvgs": touched,
            "avg_fvg_size": avg_size,
        }
