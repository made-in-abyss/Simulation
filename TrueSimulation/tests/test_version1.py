"""
Unit and integration tests for Version 1 core market mechanics:
OrderBook -> Market Orders -> Matching -> Price Formation -> Executed Trades.
"""

import unittest
from market.order import Order, OrderType, Side
from market.order_book import OrderBook
from market.matching_engine import MatchingEngine


class TestVersion1MarketMechanics(unittest.TestCase):
    def setUp(self):
        self.book = OrderBook(initial_price=100.00, tick_size=0.01)
        self.engine = MatchingEngine(self.book)

    def test_order_lifecycle(self):
        order = Order(
            order_id=1,
            trader_id="trader_1",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=100.00,
            quantity=100.0,
        )
        self.assertEqual(order.remaining_quantity, 100.0)
        self.assertFalse(order.is_filled)

        filled = order.fill(40.0)
        self.assertEqual(filled, 40.0)
        self.assertEqual(order.remaining_quantity, 60.0)
        self.assertFalse(order.is_filled)

        filled = order.fill(70.0)  # requests more than remaining
        self.assertEqual(filled, 60.0)
        self.assertEqual(order.remaining_quantity, 0.0)
        self.assertTrue(order.is_filled)

    def test_order_book_depth_and_spread(self):
        # Insert bids
        self.engine.submit_order(Order(1, "mm1", Side.BUY, OrderType.LIMIT, 99.98, 50.0))
        self.engine.submit_order(Order(2, "mm1", Side.BUY, OrderType.LIMIT, 99.99, 70.0))
        self.engine.submit_order(Order(3, "mm1", Side.BUY, OrderType.LIMIT, 100.00, 100.0))

        # Insert asks
        self.engine.submit_order(Order(4, "mm1", Side.SELL, OrderType.LIMIT, 100.02, 80.0))
        self.engine.submit_order(Order(5, "mm1", Side.SELL, OrderType.LIMIT, 100.03, 120.0))
        self.engine.submit_order(Order(6, "mm1", Side.SELL, OrderType.LIMIT, 100.05, 200.0))

        self.assertEqual(self.book.best_bid, 100.00)
        self.assertEqual(self.book.best_ask, 100.02)
        self.assertEqual(self.book.spread, 0.02)
        self.assertEqual(self.book.mid_price, 100.01)

        bids = self.book.get_bid_depth(5)
        self.assertEqual(bids[0], (100.00, 100.0))
        self.assertEqual(bids[1], (99.99, 70.0))
        self.assertEqual(bids[2], (99.98, 50.0))

        asks = self.book.get_ask_depth(5)
        self.assertEqual(asks[0], (100.02, 80.0))
        self.assertEqual(asks[1], (100.03, 120.0))
        self.assertEqual(asks[2], (100.05, 200.0))

    def test_market_buy_eating_liquidity_and_moving_price(self):
        # Set up asks: 100.01 (qty 50), 100.02 (qty 100), 100.03 (qty 150)
        self.engine.submit_order(Order(1, "mm", Side.SELL, OrderType.LIMIT, 100.01, 50.0))
        self.engine.submit_order(Order(2, "mm", Side.SELL, OrderType.LIMIT, 100.02, 100.0))
        self.engine.submit_order(Order(3, "mm", Side.SELL, OrderType.LIMIT, 100.03, 150.0))

        # Market buy of 120 units
        # Should consume: 50 @ 100.01, then 70 @ 100.02
        buy_order = Order(10, "agg_buyer", Side.BUY, OrderType.MARKET, None, 120.0)
        trades = self.engine.submit_order(buy_order, timestamp=1)

        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0].price, 100.01)
        self.assertEqual(trades[0].quantity, 50.0)
        self.assertEqual(trades[0].side, Side.BUY)
        self.assertEqual(trades[1].price, 100.02)
        self.assertEqual(trades[1].quantity, 70.0)

        # Price moved up to 100.02!
        self.assertEqual(self.book.last_trade_price, 100.02)
        # Best ask is still 100.02, with 30 units remaining
        self.assertEqual(self.book.best_ask, 100.02)
        self.assertAlmostEqual(self.book.get_level_quantity(Side.SELL, 100.02), 30.0)

        # Now sweep the remaining 30 and go to next level
        sweep_order = Order(11, "agg_buyer_2", Side.BUY, OrderType.MARKET, None, 50.0)
        trades2 = self.engine.submit_order(sweep_order, timestamp=2)
        self.assertEqual(len(trades2), 2)
        self.assertEqual(trades2[0].price, 100.02)
        self.assertEqual(trades2[0].quantity, 30.0)
        self.assertEqual(trades2[1].price, 100.03)
        self.assertEqual(trades2[1].quantity, 20.0)

        # Best ask has now moved up to 100.03 with 130 remaining
        self.assertEqual(self.book.best_ask, 100.03)
        self.assertEqual(self.book.last_trade_price, 100.03)
        self.assertAlmostEqual(self.book.get_level_quantity(Side.SELL, 100.03), 130.0)

    def test_market_sell_eating_liquidity_and_moving_price_down(self):
        # Set up bids: 99.99 (qty 40), 99.98 (qty 60), 99.95 (qty 200)
        self.engine.submit_order(Order(1, "mm", Side.BUY, OrderType.LIMIT, 99.99, 40.0))
        self.engine.submit_order(Order(2, "mm", Side.BUY, OrderType.LIMIT, 99.98, 60.0))
        self.engine.submit_order(Order(3, "mm", Side.BUY, OrderType.LIMIT, 99.95, 200.0))

        # Market sell of 110 units: sweeps 40 @ 99.99, 60 @ 99.98, 10 @ 99.95
        sell_order = Order(20, "agg_seller", Side.SELL, OrderType.MARKET, None, 110.0)
        trades = self.engine.submit_order(sell_order, timestamp=5)

        self.assertEqual(len(trades), 3)
        self.assertEqual(trades[0].price, 99.99)
        self.assertEqual(trades[1].price, 99.98)
        self.assertEqual(trades[2].price, 99.95)
        self.assertEqual(trades[2].quantity, 10.0)

        # Price dropped down to 99.95
        self.assertEqual(self.book.last_trade_price, 99.95)
        self.assertEqual(self.book.best_bid, 99.95)
        self.assertAlmostEqual(self.book.get_level_quantity(Side.BUY, 99.95), 190.0)

    def test_crossing_limit_order_creates_execution_and_resting_remainder(self):
        # Resting ask at 100.02 (qty 50)
        self.engine.submit_order(Order(1, "mm", Side.SELL, OrderType.LIMIT, 100.02, 50.0))
        self.assertEqual(self.book.best_ask, 100.02)

        # Incoming crossing limit buy at 100.05 for 80 units
        # Should match 50 @ 100.02, and remaining 30 rests at 100.05 as new best bid!
        cross_order = Order(2, "trader", Side.BUY, OrderType.LIMIT, 100.05, 80.0)
        trades = self.engine.submit_order(cross_order, timestamp=10)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].price, 100.02)
        self.assertEqual(trades[0].quantity, 50.0)
        self.assertEqual(self.book.best_bid, 100.05)
        self.assertAlmostEqual(self.book.get_level_quantity(Side.BUY, 100.05), 30.0)
        self.assertIsNone(self.book.best_ask)

    def test_cancellation(self):
        order = Order(1, "mm", Side.BUY, OrderType.LIMIT, 100.00, 100.0)
        self.engine.submit_order(order)
        self.assertEqual(self.book.best_bid, 100.00)

        cancelled = self.book.cancel_order(1)
        self.assertIsNotNone(cancelled)
        self.assertIsNone(self.book.best_bid)


if __name__ == "__main__":
    unittest.main()
