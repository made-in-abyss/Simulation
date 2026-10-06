"""
Unit tests for Version 4: Liquidity pools, latent stop triggers, and sweep detection.
"""

import unittest
import numpy as np

from market.order_book import OrderBook
from market.liquidity_pool import LatentLiquidityManager, LiquidityType
from analytics.liquidity import LiquidityDetector
from analytics.candle import Candle


class TestVersion4Liquidity(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(123)
        self.book = OrderBook(initial_price=100.0, tick_size=0.01)
        self.mgr = LatentLiquidityManager(self.book)

    def test_pool_registration_and_triggers(self):
        # Register BSL at 105.00 with 150 units volume
        bsl = self.mgr.register_pool(LiquidityType.BSL, price=105.00, volume=150.0, tick=1)
        # Register SSL at 95.00 with 120 units volume
        ssl = self.mgr.register_pool(LiquidityType.SSL, price=95.00, volume=120.0, tick=1)

        self.assertEqual(len(self.mgr.active_bsl_pools), 1)
        self.assertEqual(len(self.mgr.active_ssl_pools), 1)

        # Current price 102.00 -> nothing triggered
        orders, swept = self.mgr.check_triggers(102.00, tick=5, order_id_counter=10, rng=self.rng)
        self.assertEqual(len(orders), 0)
        self.assertEqual(len(swept), 0)
        self.assertFalse(bsl.is_swept)

        # Price sweeps BSL at 105.05 -> trigger!
        orders, swept = self.mgr.check_triggers(105.05, tick=10, order_id_counter=10, rng=self.rng)
        self.assertEqual(len(swept), 1)
        self.assertEqual(swept[0].pool_type, LiquidityType.BSL)
        self.assertTrue(bsl.is_swept)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side.value, "buy")  # Stop-run buy order
        self.assertGreater(orders[0].quantity, 30.0)

    def test_sweep_outcome_classification(self):
        detector = LiquidityDetector(observation_window_candles=2)
        bsl = self.mgr.register_pool(LiquidityType.BSL, price=105.00, volume=100.0, tick=10)
        bsl.is_swept = True
        bsl.swept_tick = 15
        bsl.swept_price = 105.20

        # Candles where price falls back down to 104.00 (Reversal)
        c0 = Candle(0, 100.0, 102.0, 100.0, 101.0, start_tick=0, end_tick=9)
        c1 = Candle(1, 101.0, 105.2, 101.0, 104.8, start_tick=10, end_tick=19)  # Sweep candle
        c2 = Candle(2, 104.8, 105.0, 103.5, 104.0, start_tick=20, end_tick=29)
        c3 = Candle(3, 104.0, 104.5, 103.0, 103.5, start_tick=30, end_tick=39)

        detector.evaluate_sweeps([bsl], [c0, c1, c2, c3])
        self.assertEqual(bsl.outcome, "reversal")

        stats = detector.get_statistics([bsl])
        self.assertEqual(stats["total_sweeps"], 1)
        self.assertEqual(stats["reversal_count"], 1)
        self.assertEqual(stats["continuation_count"], 0)


if __name__ == "__main__":
    unittest.main()
