"""
Market Structure Detector identifying Swings (HH, HL, LH, LL),
Break of Structure (BOS), and Change of Character (CHoCH).
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from analytics.candle import Candle


class SwingType(str, Enum):
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


class StructureLabel(str, Enum):
    HH = "HH"  # Higher High
    LH = "LH"  # Lower High
    HL = "HL"  # Higher Low
    LL = "LL"  # Lower Low


class BreakType(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"      # Trend continuation break above swing high
    BOS_BEARISH = "BOS_BEARISH"      # Trend continuation break below swing low
    CHOCH_BULLISH = "CHOCH_BULLISH"  # Structural reversal break above lower high
    CHOCH_BEARISH = "CHOCH_BEARISH"  # Structural reversal break below higher low


@dataclass
class SwingPoint:
    """Represents a validated swing high or low."""
    candle_index: int
    swing_type: SwingType
    price: float
    label: Optional[StructureLabel] = None
    broken: bool = False
    broken_by_candle: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candle_index": self.candle_index,
            "type": self.swing_type.value,
            "price": self.price,
            "label": self.label.value if self.label else None,
            "broken": self.broken,
            "broken_by_candle": self.broken_by_candle,
        }


@dataclass
class StructureEvent:
    """Represents a BOS or CHoCH structural break event."""
    candle_index: int
    event_type: BreakType
    level_price: float
    broken_swing_index: int
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candle_index": self.candle_index,
            "event_type": self.event_type.value,
            "level_price": self.level_price,
            "broken_swing_index": self.broken_swing_index,
            "description": self.description,
        }


class MarketStructureDetector:
    """
    Algorithmic detector of swings, BOS, and CHoCH from OHLCV candles.
    """

    def __init__(self, swing_window: int = 2):
        self.swing_window = max(1, swing_window)
        self.swings: List[SwingPoint] = []
        self.events: List[StructureEvent] = []
        self.current_trend: str = "neutral"  # "bullish", "bearish", "neutral"
        self._last_evaluated_candle = 0

    @property
    def swing_highs(self) -> List[SwingPoint]:
        return [s for s in self.swings if s.swing_type == SwingType.SWING_HIGH]

    @property
    def swing_lows(self) -> List[SwingPoint]:
        return [s for s in self.swings if s.swing_type == SwingType.SWING_LOW]

    def update(self, candles: List[Candle]) -> None:
        """
        Processes candles to detect new swings and check for structural breaks.
        """
        w = self.swing_window
        n = len(candles)
        if n < 2 * w + 1:
            return

        start_check = max(w, self._last_evaluated_candle)
        end_check = n - 1 - w

        # 1. Identify new swing highs and lows
        for i in range(start_check, end_check + 1):
            target = candles[i]

            # Swing High Check: high strictly higher than surrounding window
            is_high = True
            for j in range(1, w + 1):
                if candles[i - j].high >= target.high or candles[i + j].high >= target.high:
                    is_high = False
                    break

            if is_high:
                prev_highs = self.swing_highs
                label = StructureLabel.HH if (not prev_highs or target.high > prev_highs[-1].price) else StructureLabel.LH
                self.swings.append(
                    SwingPoint(candle_index=i, swing_type=SwingType.SWING_HIGH, price=target.high, label=label)
                )

            # Swing Low Check: low strictly lower than surrounding window
            is_low = True
            for j in range(1, w + 1):
                if candles[i - j].low <= target.low or candles[i + j].low <= target.low:
                    is_low = False
                    break

            if is_low:
                prev_lows = self.swing_lows
                label = StructureLabel.HL if (not prev_lows or target.low > prev_lows[-1].price) else StructureLabel.LL
                self.swings.append(
                    SwingPoint(candle_index=i, swing_type=SwingType.SWING_LOW, price=target.low, label=label)
                )

        self._last_evaluated_candle = end_check + 1

        # 2. Check for structural breaks (BOS and CHoCH) in sequential order
        # Iterate through candles to see which unbroken swings are broken by closes
        for c in candles:
            # Check unbroken swing highs
            for sh in self.swing_highs:
                if not sh.broken and c.index > sh.candle_index:
                    if c.close > sh.price:
                        sh.broken = True
                        sh.broken_by_candle = c.index

                        if self.current_trend == "bearish":
                            event_type = BreakType.CHOCH_BULLISH
                            self.current_trend = "bullish"
                            desc = f"Bullish CHoCH: Close {c.close:.2f} broke lower high {sh.price:.2f}"
                        else:
                            event_type = BreakType.BOS_BULLISH
                            self.current_trend = "bullish"
                            desc = f"Bullish BOS: Close {c.close:.2f} broke swing high {sh.price:.2f}"

                        self.events.append(
                            StructureEvent(
                                candle_index=c.index,
                                event_type=event_type,
                                level_price=sh.price,
                                broken_swing_index=sh.candle_index,
                                description=desc,
                            )
                        )

            # Check unbroken swing lows
            for sl in self.swing_lows:
                if not sl.broken and c.index > sl.candle_index:
                    if c.close < sl.price:
                        sl.broken = True
                        sl.broken_by_candle = c.index

                        if self.current_trend == "bullish":
                            event_type = BreakType.CHOCH_BEARISH
                            self.current_trend = "bearish"
                            desc = f"Bearish CHoCH: Close {c.close:.2f} broke higher low {sl.price:.2f}"
                        else:
                            event_type = BreakType.BOS_BEARISH
                            self.current_trend = "bearish"
                            desc = f"Bearish BOS: Close {c.close:.2f} broke swing low {sl.price:.2f}"

                        self.events.append(
                            StructureEvent(
                                candle_index=c.index,
                                event_type=event_type,
                                level_price=sl.price,
                                broken_swing_index=sl.candle_index,
                                description=desc,
                            )
                        )

    def get_summary(self) -> Dict[str, Any]:
        bos_bull = sum(1 for e in self.events if e.event_type == BreakType.BOS_BULLISH)
        bos_bear = sum(1 for e in self.events if e.event_type == BreakType.BOS_BEARISH)
        choch_bull = sum(1 for e in self.events if e.event_type == BreakType.CHOCH_BULLISH)
        choch_bear = sum(1 for e in self.events if e.event_type == BreakType.CHOCH_BEARISH)

        return {
            "total_swings": len(self.swings),
            "swing_highs": len(self.swing_highs),
            "swing_lows": len(self.swing_lows),
            "total_bos": bos_bull + bos_bear,
            "bos_bullish": bos_bull,
            "bos_bearish": bos_bear,
            "total_choch": choch_bull + choch_bear,
            "choch_bullish": choch_bull,
            "choch_bearish": choch_bear,
            "current_trend": self.current_trend,
        }
