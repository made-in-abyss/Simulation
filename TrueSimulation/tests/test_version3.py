"""
Unit tests for Version 3: Multiple participants and market regimes.
"""

import unittest
import numpy as np

from market.order import Side, OrderType
from market.order_book import OrderBook
from market.regimes import MarketRegime, RegimeManager, DEFAULT_REGIME_PROFILES
from market.participants.market_maker import MarketMaker
from market.participants.momentum_trader import MomentumTrader
from market.participants.mean_reversion_trader import MeanReversionTrader
from market.participants.institutional import InstitutionalTrader
from market.participants.noise_trader import NoiseTrader


class TestVersion3ParticipantsAndRegimes(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(42)
        self.book = OrderBook(initial_price=100.0, tick_size=0.01)

    def test_regime_manager_transitions(self):
        mgr = RegimeManager(initial_regime=MarketRegime.RANGE, transition_probability=0.0, seed=42)
        self.assertEqual(mgr.current_regime, MarketRegime.RANGE)
        self.assertEqual(mgr.current_profile.regime, MarketRegime.RANGE)

        # Force transition
        mgr.set_regime(MarketRegime.HIGH_VOLATILITY)
        self.assertEqual(mgr.current_regime, MarketRegime.HIGH_VOLATILITY)
        self.assertGreater(mgr.current_profile.volatility_mult, 2.0)
        self.assertGreater(mgr.current_profile.mm_spread_ticks, 3)

    def test_market_maker_quotes_and_volatility_widening(self):
        mm = MarketMaker("MM", levels_per_side=3, base_size=50.0)

        # In tight range regime: spread should be tight
        range_profile = DEFAULT_REGIME_PROFILES[MarketRegime.RANGE]
        _, orders_range = mm.generate_actions(self.book, range_profile, self.rng, 1, 100, [100.0])
        self.assertTrue(len(orders_range) > 0)

        best_bid_p = max(o.price for o in orders_range if o.side == Side.BUY)
        best_ask_p = min(o.price for o in orders_range if o.side == Side.SELL)
        tight_spread = round(best_ask_p - best_bid_p, 2)

        # In high volatility regime: spread should widen
        vol_profile = DEFAULT_REGIME_PROFILES[MarketRegime.HIGH_VOLATILITY]
        _, orders_vol = mm.generate_actions(self.book, vol_profile, self.rng, 1, 200, [100.0])
        best_bid_vol = max(o.price for o in orders_vol if o.side == Side.BUY)
        best_ask_vol = min(o.price for o in orders_vol if o.side == Side.SELL)
        wide_spread = round(best_ask_vol - best_bid_vol, 2)

        self.assertGreater(wide_spread, tight_spread)

    def test_momentum_trader_reaction(self):
        mom = MomentumTrader("MOM", lookback=5, threshold_ticks=2.0)
        profile = DEFAULT_REGIME_PROFILES[MarketRegime.TRENDING_BULLISH]

        # Flat prices -> no momentum order
        _, orders_flat = mom.generate_actions(self.book, profile, self.rng, 1, 100, [100.0] * 10)
        self.assertEqual(len(orders_flat), 0)

        # Strong surge up: 100.00 -> 100.20 (+20 ticks)
        surging_prices = [100.00, 100.02, 100.05, 100.10, 100.15, 100.20]
        _, orders_surge = mom.generate_actions(self.book, profile, self.rng, 2, 200, surging_prices)
        self.assertEqual(len(orders_surge), 1)
        self.assertEqual(orders_surge[0].side, Side.BUY)
        self.assertEqual(orders_surge[0].order_type, OrderType.MARKET)

    def test_mean_reversion_trader_reaction(self):
        mr = MeanReversionTrader("MR", lookback=10, stretch_ticks_threshold=5.0)
        profile = DEFAULT_REGIME_PROFILES[MarketRegime.RANGE]

        # Stable prices around 100.0
        prices = [100.0] * 10
        _, orders_idle = mr.generate_actions(self.book, profile, self.rng, 1, 100, prices)
        self.assertEqual(len(orders_idle), 0)

        # Price spiked to 101.00 (mean ~ 100.09, deviation ~ 91 ticks)
        spike_prices = [100.0] * 9 + [101.00]
        _, orders_spike = mr.generate_actions(self.book, profile, self.rng, 2, 200, spike_prices)
        self.assertEqual(len(orders_spike), 1)
        self.assertEqual(orders_spike[0].side, Side.SELL)  # Fades the spike!

    def test_institutional_trader_shock(self):
        inst = InstitutionalTrader("INST", base_block_size=200.0, institutional_frequency_mult=100.0)
        profile = DEFAULT_REGIME_PROFILES[MarketRegime.HIGH_VOLATILITY]
        _, orders = inst.generate_actions(self.book, profile, self.rng, 1, 100, [100.0])
        self.assertTrue(len(orders) > 0)
        self.assertGreater(orders[0].quantity, 30.0)  # Substantial child order slice


if __name__ == "__main__":
    unittest.main()
