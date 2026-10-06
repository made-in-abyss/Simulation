"""
Unit tests for complete SimulationEngine, seed reproducibility, and Backtesting API.
"""

import unittest
from simulation.engine import MarketConfig, SimulationEngine
from simulation.backtester import Strategy, BacktestEngine


class TestSimulationEngineAndBacktest(unittest.TestCase):
    def test_seed_reproducibility(self):
        cfg1 = MarketConfig(total_ticks=60, seed=999)
        cfg2 = MarketConfig(total_ticks=60, seed=999)
        cfg3 = MarketConfig(total_ticks=60, seed=888)

        engine1 = SimulationEngine(cfg1)
        res1 = engine1.run()

        engine2 = SimulationEngine(cfg2)
        res2 = engine2.run()

        engine3 = SimulationEngine(cfg3)
        res3 = engine3.run()

        # Identical seeds must produce identical trade counts and final prices
        self.assertEqual(res1["statistics"]["total_trades"], res2["statistics"]["total_trades"])
        self.assertEqual(res1["statistics"]["last_price"], res2["statistics"]["last_price"])
        self.assertEqual(res1["candles"], res2["candles"])

        # Different seed produces different results
        self.assertNotEqual(res1["statistics"]["last_price"], res3["statistics"]["last_price"])

    def test_full_engine_run_structures(self):
        cfg = MarketConfig(total_ticks=120, ticks_per_candle=10, seed=42)
        engine = SimulationEngine(cfg)
        res = engine.run()

        stats = res["statistics"]
        self.assertGreater(stats["total_trades"], 10)
        self.assertGreater(len(res["candles"]), 5)
        self.assertIn("total_swings", stats)
        self.assertIn("total_fvgs", stats)
        self.assertIn("total_sweeps", stats)

    def test_backtest_strategy(self):
        class SimpleBuyer(Strategy):
            def on_candle(self, candle, eng):
                if candle.is_bullish and self.position == 0:
                    self.buy_market(eng, 10.0)
                elif candle.is_bearish and self.position > 0:
                    self.sell_market(eng, 10.0)

        cfg = MarketConfig(total_ticks=100, seed=777)
        engine = SimulationEngine(cfg)
        bt = BacktestEngine(engine, SimpleBuyer("TestBuyer"))
        results = bt.run()

        self.assertIn("final_equity", results)
        self.assertIn("total_trades", results)


if __name__ == "__main__":
    unittest.main()
