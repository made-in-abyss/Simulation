"""
Console CLI runner for the Realistic Financial Market Simulator.
Runs a full market simulation from command line, printing order flow,
candle formation, market structure, sweeps, FVGs, and comprehensive statistics.
"""

import sys
import os

# Add simulator root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from simulation.engine import MarketConfig, SimulationEngine


import argparse

def main():
    parser = argparse.ArgumentParser(description="Run realistic financial market simulation from CLI.")
    parser.add_argument("pos_seed", nargs="?", type=int, default=None, help="Random seed (positional)")
    parser.add_argument("pos_ticks", nargs="?", type=int, default=None, help="Total ticks (positional)")
    parser.add_argument("--seed", type=int, default=12345, help="Random seed")
    parser.add_argument("--ticks", type=int, default=1200, help="Total simulation ticks")
    parser.add_argument("--timeframe", type=int, default=60, help="Ticks per candle (e.g. 60 = 1 min)")
    parser.add_argument("--price", type=float, default=100.0, help="Initial price")

    args = parser.parse_args()
    seed = args.pos_seed if args.pos_seed is not None else args.seed
    ticks = args.pos_ticks if args.pos_ticks is not None else args.ticks
    timeframe = args.timeframe

    print("\n" + "=" * 70)
    print(f" RUNNING REALISTIC FINANCIAL MARKET SIMULATION (Seed: {seed}, Ticks: {ticks}, Timeframe: {timeframe}s)")
    print("=" * 70)

    config = MarketConfig(
        initial_price=args.price,
        ticks_per_candle=timeframe,
        total_ticks=ticks,
        seed=seed,
        volatility_scale=1.0,
        institutional_frequency=1.0,
    )

    engine = SimulationEngine(config)
    results = engine.run()
    stats = results["statistics"]

    print(f"\n[SUMMARY METRICS]")
    print(f"Total Ticks Simulated: {ticks}")
    print(f"Candles Formed:        {stats['candle_count']}")
    print(f"First Price:           {stats['first_price']:.2f}")
    print(f"High / Low Price:      {stats['high_price']:.2f} / {stats['low_price']:.2f}")
    print(f"Last Price:            {stats['last_price']:.2f}")
    print(f"Total Return:          {stats['total_return_pct']:+.2f}%")
    print(f"Annualized Volatility: {stats['annualized_vol_pct']:.2f}%")
    print(f"Max Drawdown:          {stats['max_drawdown_pct']:.2f}%")

    print(f"\n[ORDER FLOW & VOLUME]")
    print(f"Total Trades:          {stats['total_trades']}")
    print(f"Total Volume:          {stats['total_volume']:,.1f}")
    print(f"Buy Volume:            {stats['buy_volume']:,.1f}")
    print(f"Sell Volume:           {stats['sell_volume']:,.1f}")
    print(f"Order Flow Delta:      {stats['volume_delta']:+,.1f}")
    print(f"Average Trade Size:    {stats['avg_trade_size']:.1f}")
    print(f"Large Block Trades:    {stats['large_trades_count']} ({stats['large_trade_volume']:,.1f} vol)")

    print(f"\n[SPREAD & LIQUIDITY]")
    print(f"Mean Spread:           {stats['spread_mean']:.4f}")
    print(f"Max Spread:            {stats['spread_max']:.4f}")
    print(f"Liquidity Sweeps:      {stats['total_sweeps']} (BSL: {stats['bsl_sweeps']}, SSL: {stats['ssl_sweeps']})")
    print(f"Sweep Outcomes:        Reversals: {stats['reversal_count']} | Continuations: {stats['continuation_count']}")

    print(f"\n[MARKET STRUCTURE & FVGs]")
    print(f"Swings Identified:     {stats['total_swings']} (Highs: {stats['swing_highs']}, Lows: {stats['swing_lows']})")
    print(f"Break of Structure:    {stats['total_bos']} (Bull: {stats['bos_bullish']}, Bear: {stats['bos_bearish']})")
    print(f"Change of Character:   {stats['total_choch']} (Bull: {stats['choch_bullish']}, Bear: {stats['choch_bearish']})")
    print(f"Active Trend State:    {stats['current_trend'].upper()}")
    print(f"Fair Value Gaps:       {stats['total_fvgs']} (Bull: {stats['bullish_fvgs']}, Bear: {stats['bearish_fvgs']})")
    print(f"FVG Lifecycle:         Filled: {stats['filled_fvgs']} | Touched: {stats['touched_fvgs']} | Active: {stats['active_fvgs']}")

    print("\n[RECENT 5 CANDLES]")
    for c in results["candles"][-5:]:
        color = "GREEN" if c["close"] >= c["open"] else "RED  "
        print(f"Candle #{c['index']:02d} [{color}] O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f} | Vol:{c['volume']:.1f} (Delta:{c['delta']:+.1f})")

    print("\n[FINAL ORDER BOOK STATE]")
    ob = results["order_book"]
    print(f"Mid Price: {ob['mid_price']:.2f} | Spread: {ob['spread'] or 0.0:.2f}")
    print("Top 3 Asks:")
    for p, q in ob["asks"][:3]:
        print(f"  ASK: {p:.2f} | Size: {q:.1f}")
    print("Top 3 Bids:")
    for p, q in ob["bids"][:3]:
        print(f"  BID: {p:.2f} | Size: {q:.1f}")

    print("\n" + "=" * 70)
    print(" Simulation completed successfully.")
    print(" To launch the interactive browser terminal, run: python run_server.py")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
