"""
Version 1 Interactive / Diagnostic Demonstration Script.

Demonstrates:
1. Order book initialization with realistic two-sided liquidity.
2. Formatted depth ladder display.
3. Market buy sweeping ask levels, moving price upward and widening spread.
4. Market maker replenishment of liquidity.
5. Large institutional market sell sweeping bid levels, moving price downward.
6. Execution and trade verification logging.
"""

import sys
import os

# Ensure current directory is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from market.order import Order, OrderType, Side
from market.order_book import OrderBook
from market.matching_engine import MatchingEngine


def print_ladder(book: OrderBook, depth_levels: int = 5):
    """Prints a clean ASCII order book ladder."""
    print("=" * 40)
    print(f"ORDER BOOK (Mid: {book.mid_price:.2f} | Spread: {book.spread or 0.0:.2f} | Last: {book.last_trade_price:.2f})")
    print(f"{'PRICE':>12} | {'QUANTITY':>10} | {'SIDE':^6}")
    print("-" * 40)

    # Asks (highest to lowest down to best ask)
    asks = book.get_ask_depth(depth_levels)
    for price, qty in reversed(asks):
        is_best = " <- BEST ASK" if price == book.best_ask else ""
        print(f"{price:>12.2f} | {qty:>10.1f} | {'ASK':^6}{is_best}")

    print("-" * 40)
    print(f"{'--- SPREAD ' + str(round(book.spread, 2)) + ' ---':^40}" if book.spread else f"{'--- EMPTY BOOK ---':^40}")
    print("-" * 40)

    # Bids (best bid down to lower bids)
    bids = book.get_bid_depth(depth_levels)
    for price, qty in bids:
        is_best = " <- BEST BID" if price == book.best_bid else ""
        print(f"{price:>12.2f} | {qty:>10.1f} | {'BID':^6}{is_best}")
    print("=" * 40)
    print(f"Total Bid Vol: {book.total_bid_volume:.1f} | Total Ask Vol: {book.total_ask_volume:.1f} | Imbalance: {book.imbalance:+.2f}\n")


def main():
    print("\n" + "#" * 60)
    print(" FINANCIAL MARKET SIMULATOR - VERSION 1 DEMO")
    print(" OrderBook -> Market Orders -> Matching -> Price Emergence")
    print("#" * 60 + "\n")

    book = OrderBook(initial_price=105.00, tick_size=0.01)
    engine = MatchingEngine(book)
    order_id = 1

    # 1. Populate initial liquidity around 105.00
    print("[STEP 1] Seeding initial order book liquidity around 105.00...")
    ask_seed = [
        (105.01, 60.0),
        (105.02, 300.0),  # Liquidity concentration
        (105.03, 80.0),
        (105.04, 120.0),
        (105.05, 250.0),
    ]
    bid_seed = [
        (104.99, 70.0),
        (104.98, 250.0),  # Liquidity concentration
        (104.97, 90.0),
        (104.96, 110.0),
        (104.95, 200.0),
    ]

    for price, qty in ask_seed:
        engine.submit_order(Order(order_id, "MM_1", Side.SELL, OrderType.LIMIT, price, qty), timestamp=0)
        order_id += 1

    for price, qty in bid_seed:
        engine.submit_order(Order(order_id, "MM_1", Side.BUY, OrderType.LIMIT, price, qty), timestamp=0)
        order_id += 1

    print_ladder(book)

    # 2. Aggressive Market Buy: 150 units
    # Will consume 60 @ 105.01, then 90 @ 105.02 (leaving 210 at 105.02)
    print("[STEP 2] Aggressive Buyer submits MARKET BUY of 150 units...")
    market_buy_1 = Order(order_id, "Momentum_Buyer_A", Side.BUY, OrderType.MARKET, None, 150.0)
    order_id += 1
    trades_1 = engine.submit_order(market_buy_1, timestamp=1)

    print(f"-> Executed {len(trades_1)} trade fills:")
    for t in trades_1:
        print(f"   {t}")
    print(f"-> New Last Trade Price: {book.last_trade_price:.2f} (Moved UP from 105.00 to 105.02)")
    print_ladder(book)

    # 3. Institutional Large Buy: 350 units
    # Remaining at 105.02 is 210 -> consumes all 210 @ 105.02
    # Then consumes 80 @ 105.03
    # Then consumes 60 @ 105.04 (leaving 60 @ 105.04)
    print("[STEP 3] Institutional Trader submits LARGE MARKET BUY of 350 units...")
    market_buy_2 = Order(order_id, "Institution_Alpha", Side.BUY, OrderType.MARKET, None, 350.0)
    order_id += 1
    trades_2 = engine.submit_order(market_buy_2, timestamp=2)

    print(f"-> Executed {len(trades_2)} trade fills sweeping multiple levels:")
    for t in trades_2:
        print(f"   {t}")
    print(f"-> Price swept upwards to {book.last_trade_price:.2f}!")
    print(f"-> Note how the spread widened to {book.spread:.2f} because ask liquidity was eaten!")
    print_ladder(book)

    # 4. Market Makers Replenish Liquidity
    print("[STEP 4] Market Makers react to spread widening by inserting new limit bids and asks...")
    engine.submit_order(Order(order_id, "MM_2", Side.BUY, OrderType.LIMIT, 105.01, 100.0), timestamp=3)
    order_id += 1
    engine.submit_order(Order(order_id, "MM_2", Side.BUY, OrderType.LIMIT, 105.03, 75.0), timestamp=3)
    order_id += 1
    engine.submit_order(Order(order_id, "MM_2", Side.SELL, OrderType.LIMIT, 105.05, 150.0), timestamp=3)
    order_id += 1
    print_ladder(book)

    # 5. Large Directional Sell Order (Institutional Sell)
    print("[STEP 5] Mean-Reversion / Institutional Seller hits the bid with MARKET SELL of 300 units...")
    market_sell = Order(order_id, "Institution_Beta", Side.SELL, OrderType.MARKET, None, 300.0)
    order_id += 1
    trades_3 = engine.submit_order(market_sell, timestamp=4)

    print(f"-> Executed {len(trades_3)} trade fills sweeping bids downward:")
    for t in trades_3:
        print(f"   {t}")
    print(f"-> Price plunged down to {book.last_trade_price:.2f}!")
    print_ladder(book)

    # Summary
    print("=" * 60)
    print("VERSION 1 VERIFICATION SUMMARY:")
    print(f"Total Trades Recorded: {engine.trade_count}")
    print(f"Total Volume Executed: {engine.total_trade_volume:.1f} units")
    print(f"Initial Mid: 105.00 -> High: 105.04 -> Final Trade: {book.last_trade_price:.2f}")
    print("Mechanism Result: Price moves strictly as a deterministic consequence")
    print("of liquidity consumption, book depletion, and resting order queues.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
