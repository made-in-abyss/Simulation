"""
Unit tests for Version 6: Fair Value Gap (FVG) detection and lifecycle tracking.
"""

import unittest
from analytics.candle import Candle
from analytics.fvg import FVGDetector, FVGType, FVGStatus


class TestVersion6FVG(unittest.TestCase):
    def test_bullish_fvg_detection_and_lifecycle(self):
        detector = FVGDetector(min_gap_size=0.1)

        # Candle 0 (C1): High = 101.0
        # Candle 1 (C2): Impulsive expansion up to 108.0
        # Candle 2 (C3): Low = 104.0, High = 109.0
        # Gap: [101.0, 104.0], size = 3.0
        c0 = Candle(0, 100.0, 101.0, 99.5, 100.5)
        c1 = Candle(1, 100.5, 108.0, 100.5, 107.5)
        c2 = Candle(2, 107.5, 109.0, 104.0, 108.5)

        detector.update([c0, c1, c2])
        self.assertEqual(len(detector.fvgs), 1)

        fvg = detector.fvgs[0]
        self.assertEqual(fvg.fvg_type, FVGType.BULLISH)
        self.assertEqual(fvg.bottom_price, 101.0)
        self.assertEqual(fvg.top_price, 104.0)
        self.assertEqual(fvg.size, 3.0)
        self.assertEqual(fvg.status, FVGStatus.ACTIVE)
        self.assertFalse(fvg.is_touched)

        # Candle 3: Tests the gap (Low = 102.5 -> 50% fill)
        c3 = Candle(3, 108.5, 108.5, 102.5, 105.0)
        detector.update([c0, c1, c2, c3])
        self.assertTrue(fvg.is_touched)
        self.assertEqual(fvg.status, FVGStatus.PARTIALLY_FILLED)
        self.assertAlmostEqual(fvg.fill_percentage, 50.0, places=1)

        # Candle 4: Trades through bottom (Low = 100.0 -> 100% fill)
        c4 = Candle(4, 105.0, 105.0, 100.0, 101.0)
        detector.update([c0, c1, c2, c3, c4])
        self.assertEqual(fvg.status, FVGStatus.FILLED)
        self.assertEqual(fvg.fill_percentage, 100.0)

    def test_bearish_fvg_detection(self):
        detector = FVGDetector(min_gap_size=0.1)

        # Candle 0 (C1): Low = 110.0
        # Candle 1 (C2): Impulsive collapse down
        # Candle 2 (C3): High = 105.0
        # Gap: [105.0, 110.0], size = 5.0
        c0 = Candle(0, 112.0, 113.0, 110.0, 111.0)
        c1 = Candle(1, 111.0, 111.0, 101.0, 102.0)
        c2 = Candle(2, 102.0, 105.0, 99.0, 100.0)

        detector.update([c0, c1, c2])
        self.assertEqual(len(detector.fvgs), 1)

        fvg = detector.fvgs[0]
        self.assertEqual(fvg.fvg_type, FVGType.BEARISH)
        self.assertEqual(fvg.bottom_price, 105.0)
        self.assertEqual(fvg.top_price, 110.0)
        self.assertEqual(fvg.size, 5.0)

        summary = detector.get_summary()
        self.assertEqual(summary["total_fvgs"], 1)
        self.assertEqual(summary["bearish_fvgs"], 1)
        self.assertEqual(summary["bullish_fvgs"], 0)


if __name__ == "__main__":
    unittest.main()
