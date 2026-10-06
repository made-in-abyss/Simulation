"""
Unit tests for Version 5: Market structure, swings, BOS, and CHoCH.
"""

import unittest
from analytics.candle import Candle
from analytics.market_structure import MarketStructureDetector, BreakType, SwingType, StructureLabel


class TestVersion5MarketStructure(unittest.TestCase):
    def test_swing_detection_and_labels(self):
        detector = MarketStructureDetector(swing_window=1)

        # Candle 0: neutral
        # Candle 1: peak at 105.0 (swing high)
        # Candle 2: valley at 95.0 (swing low, between 100 and 99)
        # Candle 3: peak at 108.0 (higher high, between 99 and 102)
        # Candle 4: valley at 98.0 (higher low, between 102 and 101)
        # Candle 5: right-side bar
        candles = [
            Candle(0, 100.0, 101.0, 99.0, 100.0),
            Candle(1, 100.0, 105.0, 100.0, 104.0),
            Candle(2, 104.0, 104.0, 95.0, 96.0),
            Candle(3, 96.0, 108.0, 100.0, 107.0),
            Candle(4, 107.0, 107.0, 98.0, 102.0),
            Candle(5, 102.0, 103.0, 101.0, 101.5),
        ]

        detector.update(candles)
        self.assertEqual(len(detector.swing_highs), 2)
        self.assertEqual(len(detector.swing_lows), 2)

        # First high at candle 1 (105.0)
        sh1 = detector.swing_highs[0]
        self.assertEqual(sh1.candle_index, 1)
        self.assertEqual(sh1.price, 105.0)

        # Second high at candle 3 (108.0) -> HH
        sh2 = detector.swing_highs[1]
        self.assertEqual(sh2.candle_index, 3)
        self.assertEqual(sh2.price, 108.0)
        self.assertEqual(sh2.label, StructureLabel.HH)

        # First low at candle 2 (95.0)
        sl1 = detector.swing_lows[0]
        self.assertEqual(sl1.candle_index, 2)
        self.assertEqual(sl1.price, 95.0)

        # Second low at candle 4 (98.0) -> HL
        sl2 = detector.swing_lows[1]
        self.assertEqual(sl2.candle_index, 4)
        self.assertEqual(sl2.price, 98.0)
        self.assertEqual(sl2.label, StructureLabel.HL)

    def test_bos_and_choch_breaks(self):
        detector = MarketStructureDetector(swing_window=1)

        # 1. Build an uptrend swing:
        # Candle 1: High at 105 (swings between c0 and c2)
        # Candle 2: Low at 100 (swings between c1 and c3)
        # Candle 3: closes at 106 (> 105) -> BOS_BULLISH!
        # Candle 4: High at 110 (swings between c3 and c5)
        # Candle 5: Low at 103 (swings between c4 and c6) -> Higher Low
        # Candle 6: High at 107
        # Candle 7: closes at 101 (< 103) -> CHOCH_BEARISH!
        candles = [
            Candle(0, 98.0, 99.0, 97.0, 98.0),
            Candle(1, 98.0, 105.0, 98.0, 104.0),
            Candle(2, 104.0, 104.0, 100.0, 101.0),
            Candle(3, 101.0, 107.0, 101.0, 106.0),  # Closes above 105 -> BOS
            Candle(4, 106.0, 110.0, 105.0, 109.0),  # Peak at 110
            Candle(5, 109.0, 109.0, 103.0, 104.0),  # Low at 103
            Candle(6, 104.0, 107.0, 104.0, 106.0),  # Peak at 107
            Candle(7, 106.0, 106.0, 100.0, 101.0),  # Closes at 101 (< 103) -> CHoCH
            Candle(8, 101.0, 102.0, 100.0, 100.5),
        ]

        detector.update(candles)
        events = detector.events
        self.assertTrue(any(e.event_type == BreakType.BOS_BULLISH for e in events))
        self.assertTrue(any(e.event_type == BreakType.CHOCH_BEARISH for e in events))
        self.assertEqual(detector.current_trend, "bearish")


if __name__ == "__main__":
    unittest.main()
