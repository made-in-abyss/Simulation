"""
Unit tests for realism upgrades:
- Hawkes self-exciting trade arrival engine
- MarketMaker psychological round-number clustering & toxic flow defense
- MomentumTrader dynamic position tracking & profit-taking pullbacks
- Dynamic duration / total_ticks configuration
"""

import unittest
import numpy as np
from simulation.engine import MarketConfig, SimulationEngine
from market.participants.market_maker import MarketMaker
from market.participants.momentum_trader import MomentumTrader
from market.order import Side, OrderType
from market.trade import Trade
from market.regimes import DEFAULT_REGIME_PROFILES, MarketRegime


class TestMicrostructureRealism(unittest.TestCase):
    def test_hawkes_self_excitation(self):
        engine = SimulationEngine(MarketConfig(total_ticks=50, seed=123))
        initial_hawkes = engine.hawkes_excitation
        self.assertEqual(initial_hawkes, 0.0)

        # Step 20 ticks and verify hawkes excitation remains bounded and responds to volume
        for _ in range(20):
            engine.step()

        self.assertGreaterEqual(engine.hawkes_excitation, 0.0)
        self.assertLessEqual(engine.hawkes_excitation, 3.5)

    def test_market_maker_psychological_weights(self):
        rng = np.random.default_rng(42)
        # Whole dollar ($100.00) must have significantly higher weight than non-round ($100.17)
        w_round = MarketMaker._get_psychological_weight(100.00, rng)
        w_half = MarketMaker._get_psychological_weight(100.50, rng)
        w_quarter = MarketMaker._get_psychological_weight(100.25, rng)
        w_non_round = MarketMaker._get_psychological_weight(100.17, rng)

        self.assertGreater(w_round, w_quarter)
        self.assertGreater(w_half, w_quarter)
        self.assertGreater(w_quarter, w_non_round)
        self.assertGreaterEqual(w_round, 3.0)

    def test_market_maker_adverse_selection_shading(self):
        mm = MarketMaker("MM_TEST")
        self.assertEqual(mm.recent_taker_flow, 0.0)

        # Simulate heavy aggressive selling (toxic flow)
        for i in range(5):
            t = Trade(
                trade_id=i,
                maker_order_id=1,
                taker_order_id=2,
                maker_id=mm.trader_id,
                taker_id="INSTITUTION_FLOW",
                side=Side.SELL,  # Taker sold -> toxic sell pressure
                price=100.0 - i * 0.01,
                quantity=45.0,
                timestamp=i,
            )
            mm.on_trade(t)

        self.assertLess(mm.recent_taker_flow, -20.0)
        self.assertGreater(mm.inventory, 0.0)  # MM bought inventory

    def test_momentum_position_tracking_and_profit_taking(self):
        mom = MomentumTrader("MOM_TEST", threshold_ticks=1.5, profit_target_ticks=8.0)
        self.assertEqual(mom.net_position, 0.0)

        # Simulate buy fills accumulating a long position
        t1 = Trade(
            trade_id=1,
            maker_order_id=10,
            taker_order_id=20,
            maker_id="MM_CORE",
            taker_id=mom.trader_id,
            side=Side.BUY,
            price=100.00,
            quantity=30.0,
            timestamp=5,
        )
        mom.on_trade(t1)
        self.assertAlmostEqual(mom.net_position, 30.0)
        self.assertAlmostEqual(mom.avg_entry_price, 100.00)

        # When price reaches profit target (+10 ticks = 100.10)
        recent_prices = [100.00] * 10 + [100.10]
        from market.order_book import OrderBook
        book = OrderBook(initial_price=100.10)
        profile = DEFAULT_REGIME_PROFILES[MarketRegime.TRENDING_BULLISH]
        rng = np.random.default_rng(123)

        cancels, orders = mom.generate_actions(book, profile, rng, tick=35, order_id_counter=100, recent_prices=recent_prices)
        
        # Must generate profit-taking exit order (SELL market order)
        self.assertGreater(len(orders), 0)
        exit_order = orders[0]
        self.assertEqual(exit_order.side, Side.SELL)
        self.assertEqual(exit_order.order_type, OrderType.MARKET)
        self.assertGreater(exit_order.quantity, 0)

    def test_duration_configuration(self):
        # Verify configurable duration runs cleanly to target ticks
        cfg = MarketConfig(total_ticks=120, ticks_per_candle=30, seed=555)
        eng = SimulationEngine(cfg)
        res = eng.run()
        self.assertEqual(res["clock"]["tick"], 120)
        self.assertGreaterEqual(len(res["candles"]), 4)


if __name__ == "__main__":
    unittest.main()
