"""
Unit tests for Version 2: Candle aggregation, order flow volume/delta, and trade statistics.
"""

import unittest
from market.trade import Trade
from market.order import Side
from analytics.candle import Candle
from analytics.candles import CandleAggregator
from analytics.trade_statistics import StatisticsEngine


class TestVersion2Analytics(unittest.TestCase):
    def test_candle_aggregation_and_delta(self):
        agg = CandleAggregator(ticks_per_candle=5, initial_price=100.0)

        # Candle 0 (ticks 0 to 4)
        t1 = Trade(1, 101, 201, "m1", "t1", Side.BUY, 100.10, 50.0, 0)
        t2 = Trade(2, 102, 202, "m2", "t2", Side.BUY, 100.20, 30.0, 1)
        t3 = Trade(3, 103, 203, "m3", "t3", Side.SELL, 100.05, 20.0, 3)

        agg.process_trade(t1)
        agg.process_trade(t2)
        agg.process_trade(t3)

        # Step clock through ticks 0..4
        for tick in range(1, 5):
            c = agg.step_tick(tick)
            self.assertIsNone(c)

        # On tick 5, candle 0 should close!
        closed = agg.step_tick(5)
        self.assertIsNotNone(closed)
        self.assertEqual(closed.index, 0)
        self.assertEqual(closed.open, 100.10)
        self.assertEqual(closed.high, 100.20)
        self.assertEqual(closed.low, 100.05)
        self.assertEqual(closed.close, 100.05)
        self.assertEqual(closed.volume, 100.0)
        self.assertEqual(closed.buy_volume, 80.0)
        self.assertEqual(closed.sell_volume, 20.0)
        self.assertEqual(closed.delta, 60.0)
        self.assertEqual(closed.trade_count, 3)
        self.assertTrue(closed.is_bearish)  # Open 100.10 > Close 100.05

        # Check volume-at-price
        self.assertEqual(closed.volume_at_price[100.10], 50.0)
        self.assertEqual(closed.volume_at_price[100.20], 30.0)
        self.assertEqual(closed.volume_at_price[100.05], 20.0)

    def test_zero_volume_candle_continuation(self):
        agg = CandleAggregator(ticks_per_candle=3, initial_price=100.0)
        # No trades happen, advance ticks
        agg.step_tick(1)
        agg.step_tick(2)
        c0 = agg.step_tick(3)
        self.assertIsNotNone(c0)
        self.assertEqual(c0.open, 100.0)
        self.assertEqual(c0.close, 100.0)
        self.assertEqual(c0.volume, 0.0)
        self.assertEqual(c0.delta, 0.0)
        self.assertEqual(c0.trade_count, 0)

    def test_statistics_engine_computation(self):
        trades = [
            Trade(1, 1, 2, "m", "t", Side.BUY, 100.0, 10.0, 1),
            Trade(2, 3, 4, "m", "t", Side.BUY, 101.0, 20.0, 2),
            Trade(3, 5, 6, "m", "t", Side.SELL, 99.0, 50.0, 3),  # Large trade
        ]

        candles = [
            Candle(0, open=100.0, high=101.0, low=99.5, close=101.0, volume=30.0, buy_volume=30.0, sell_volume=0.0, delta=30.0, trade_count=2),
            Candle(1, open=101.0, high=101.5, low=98.5, close=99.0, volume=50.0, buy_volume=0.0, sell_volume=50.0, delta=-50.0, trade_count=1),
        ]

        spreads = [0.02, 0.03, 0.05]
        stats = StatisticsEngine.compute(trades, candles, spreads, large_trade_multiplier=1.8)

        self.assertEqual(stats["total_trades"], 3)
        self.assertEqual(stats["total_volume"], 80.0)
        self.assertEqual(stats["buy_volume"], 30.0)
        self.assertEqual(stats["sell_volume"], 50.0)
        self.assertEqual(stats["volume_delta"], -20.0)
        self.assertEqual(stats["candle_count"], 2)
        self.assertEqual(stats["first_price"], 100.0)
        self.assertEqual(stats["last_price"], 99.0)
        self.assertEqual(stats["total_return_pct"], -1.0)
        self.assertEqual(stats["large_trades_count"], 1)  # 50 > 1.8 * 26.67
        self.assertAlmostEqual(stats["spread_mean"], 0.0333, places=3)


if __name__ == "__main__":
    unittest.main()
