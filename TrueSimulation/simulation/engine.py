"""
Market Simulation Engine orchestrating all market microstructure layers:
Simulation Clock -> Participants -> Orders -> OrderBook -> MatchingEngine ->
1-Second Trades -> Real-Time Open Candle -> Market Structure -> Sweeps -> FVGs -> Event Feed.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from market.order import Order, OrderType, Side
from market.order_book import OrderBook
from market.matching_engine import MatchingEngine
from market.trade import Trade
from market.regimes import MarketRegime, RegimeManager, RegimeProfile, DEFAULT_REGIME_PROFILES
from market.participants.base import Participant
from market.participants.market_maker import MarketMaker
from market.participants.momentum_trader import MomentumTrader
from market.participants.mean_reversion_trader import MeanReversionTrader
from market.participants.noise_trader import NoiseTrader
from market.participants.institutional import InstitutionalTrader
from market.liquidity_pool import LatentLiquidityManager, LiquidityType, LiquidityPool
from analytics.candle import Candle
from analytics.candles import CandleAggregator, format_sim_time
from analytics.market_structure import MarketStructureDetector, SwingPoint, StructureEvent
from analytics.liquidity import LiquidityDetector
from analytics.fvg import FVGDetector, FairValueGap
from analytics.trade_statistics import StatisticsEngine


@dataclass
class MarketConfig:
    """Configuration parameters for the market simulation."""
    initial_price: float = 100.0
    tick_size: float = 0.01
    ticks_per_candle: int = 60          # Default: 60 seconds = 1 minute candle
    tick_duration_seconds: float = 1.0  # 1 simulation tick = 1 second
    total_ticks: int = 1200             # 20 minutes of 1-second ticks
    seed: int = 12345

    # Behavioral scale factors
    volatility_scale: float = 1.0
    momentum_scale: float = 1.0
    mean_reversion_scale: float = 1.0
    institutional_frequency: float = 1.0
    mm_activity: float = 1.0
    initial_liquidity_depth: int = 15
    initial_liquidity_size: float = 45.0
    swing_window: int = 2
    min_fvg_size: float = 0.01


@dataclass
class MarketEvent:
    """Real-time event record for the live terminal event feed."""
    tick: int
    time_str: str
    category: str      # "order", "spread", "liquidity", "sweep", "structure", "fvg", "regime"
    title: str
    detail: str
    sentiment: str     # "bull", "bear", "neutral", "gold", "purple", "cyan"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "time_str": self.time_str,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "sentiment": self.sentiment,
        }


@dataclass
class StepSnapshot:
    """Snapshot of the market state at a specific 1-second simulation tick."""
    tick: int
    time_str: str
    price: float
    mid_price: float
    spread: Optional[float]
    regime: str
    imbalance: float
    tick_volume: float
    tick_delta: float
    tick_trades_count: int
    recent_trades: List[Dict[str, Any]]
    completed_candles_count: int
    live_open_candle: Optional[Dict[str, Any]]
    total_volume: float
    total_delta: float
    total_trades: int
    new_events: List[Dict[str, Any]]


class SimulationEngine:
    """
    Central orchestration engine for the realistic financial market simulator.
    Advances in discrete 1-second logical ticks. Current candle updates continuously intra-bar.
    """

    def __init__(self, config: Optional[MarketConfig] = None):
        self.config = config or MarketConfig()
        self.seed = self.config.seed
        self.rng = np.random.default_rng(self.seed)

        # Core market layers
        self.book = OrderBook(initial_price=self.config.initial_price, tick_size=self.config.tick_size)
        self.matching_engine = MatchingEngine(self.book)
        self.regime_manager = RegimeManager(
            initial_regime=MarketRegime.RANGE,
            transition_probability=0.008,
            seed=int(self.rng.integers(1, 1000000)),
        )

        # Participants with calibrated activity for 1-second ticks
        self.participants: List[Participant] = [
            MarketMaker("MM_CORE", levels_per_side=self.config.initial_liquidity_depth, base_size=self.config.initial_liquidity_size * self.config.mm_activity),
            MomentumTrader("MOMENTUM_POOL", lookback=8, threshold_ticks=2.0),
            MeanReversionTrader("MEAN_REV_POOL", lookback=18, stretch_ticks_threshold=4.5),
            NoiseTrader("NOISE_RETAIL", base_size=10.0, activity_rate=0.55),
            InstitutionalTrader("INSTITUTION_FLOW", base_block_size=160.0, institutional_frequency_mult=self.config.institutional_frequency),
        ]

        # Liquidity and Latent Stop management
        self.latent_liquidity = LatentLiquidityManager(self.book)

        # Analytics layers
        self.candle_aggregator = CandleAggregator(
            ticks_per_candle=self.config.ticks_per_candle,
            initial_price=self.config.initial_price,
        )
        self.market_structure = MarketStructureDetector(swing_window=self.config.swing_window)
        self.liquidity_detector = LiquidityDetector(observation_window_candles=2)
        self.fvg_detector = FVGDetector(min_gap_size=self.config.min_fvg_size)

        # Runtime state
        self.current_tick = 0
        self.order_counter = 0
        self.spread_history: List[float] = []
        self.price_history: List[float] = [self.config.initial_price]
        self.snapshots: List[StepSnapshot] = []
        self.event_feed: List[MarketEvent] = []
        self.tick_history: List[Dict[str, Any]] = []
        self.hawkes_excitation: float = 0.0

        # Tracking sets to avoid redundant notifications
        self._registered_swing_high_indices = set()
        self._registered_swing_low_indices = set()
        self._notified_approaches = set()
        self._last_fvg_count = 0
        self._last_bos_count = 0
        self._last_choch_count = 0
        self._prev_regime = MarketRegime.RANGE

        # Seed initial order book liquidity
        self._seed_initial_book()

    @property
    def current_time_str(self) -> str:
        return format_sim_time(self.current_tick)

    def _seed_initial_book(self) -> None:
        """Populates realistic initial resting limit orders around starting price."""
        mid = self.config.initial_price
        ts = self.config.tick_size
        depth = max(12, self.config.initial_liquidity_depth)
        base_sz = max(40.0, self.config.initial_liquidity_size)

        for i in range(1, depth + 1):
            bid_p = self.book.round(mid - i * ts)
            ask_p = self.book.round(mid + i * ts)

            curve_mult = 0.50 + 0.25 * np.sqrt(i)
            concentration = 1.8 if (i in (4, 9)) else 1.0
            bid_sz = round(base_sz * curve_mult * concentration * self.rng.uniform(0.85, 1.25), 1)
            ask_sz = round(base_sz * curve_mult * concentration * self.rng.uniform(0.85, 1.25), 1)

            self.order_counter += 1
            self.matching_engine.submit_order(
                Order(self.order_counter, "MM_SEED", Side.BUY, OrderType.LIMIT, bid_p, bid_sz),
                timestamp=0,
            )
            self.order_counter += 1
            self.matching_engine.submit_order(
                Order(self.order_counter, "MM_SEED", Side.SELL, OrderType.LIMIT, ask_p, ask_sz),
                timestamp=0,
            )

    def _add_event(self, category: str, title: str, detail: str, sentiment: str = "neutral") -> MarketEvent:
        event = MarketEvent(
            tick=self.current_tick,
            time_str=self.current_time_str,
            category=category,
            title=title,
            detail=detail,
            sentiment=sentiment,
        )
        self.event_feed.append(event)
        if len(self.event_feed) > 300:
            self.event_feed.pop(0)
        return event

    def step(self) -> StepSnapshot:
        """
        Executes one discrete 1-second simulation tick.
        The current candle updates continuously intra-bar as trades execute.
        """
        self.current_tick += 1
        tick = self.current_tick
        time_str = self.current_time_str
        tick_events: List[MarketEvent] = []

        # 1. Update Market Regime
        regime = self.regime_manager.step()
        base_profile = self.regime_manager.current_profile

        # Endogenous Hawkes self-exciting volatility modulation
        self.hawkes_excitation *= 0.88
        excitation_mult = 0.85 + 0.30 * self.hawkes_excitation

        profile = RegimeProfile(
            regime=base_profile.regime,
            directional_drift=base_profile.directional_drift,
            momentum_sensitivity=base_profile.momentum_sensitivity * min(2.0, excitation_mult),
            mean_reversion_strength=base_profile.mean_reversion_strength,
            volatility_mult=base_profile.volatility_mult * self.config.volatility_scale * excitation_mult,
            mm_spread_ticks=base_profile.mm_spread_ticks,
            mm_depth_mult=base_profile.mm_depth_mult,
            large_order_prob=base_profile.large_order_prob * min(2.5, excitation_mult),
            noise_activity=base_profile.noise_activity * min(2.0, excitation_mult),
        )

        if regime != self._prev_regime:
            e = self._add_event(
                category="regime",
                title="Regime Shift",
                detail=f"Market transitioned to {regime.value.replace('_', ' ').title()}",
                sentiment="gold",
            )
            tick_events.append(e)
            self._prev_regime = regime

        # 2. Check Proximity to Latent Liquidity Pools & Stop Triggers
        curr_price = self.book.last_trade_price
        for pool in self.latent_liquidity.pools:
            if not pool.is_swept and pool.pool_id not in self._notified_approaches:
                if abs(curr_price - pool.price) <= 0.02:
                    self._notified_approaches.add(pool.pool_id)
                    e = self._add_event(
                        category="liquidity",
                        title=f"{pool.pool_type.value} Approached",
                        detail=f"Price near {pool.pool_type.value} liquidity at {pool.price:.2f}",
                        sentiment="purple",
                    )
                    tick_events.append(e)

        stop_orders, swept_pools = self.latent_liquidity.check_triggers(
            curr_price, tick, self.order_counter, self.rng
        )
        self.order_counter += len(stop_orders)

        for sp in swept_pools:
            sent = "bull" if sp.pool_type == LiquidityType.BSL else "bear"
            e = self._add_event(
                category="sweep",
                title=f"{sp.pool_type.value} Swept",
                detail=f"Price traded through {sp.pool_type.value} level at {sp.price:.2f}",
                sentiment=sent,
            )
            tick_events.append(e)

        # 3. Gather Participant Actions
        all_cancels: List[int] = []
        all_new_orders: List[Order] = list(stop_orders)

        for p in self.participants:
            cancels, orders = p.generate_actions(
                self.book, profile, self.rng, tick, self.order_counter, self.price_history
            )
            all_cancels.extend(cancels)
            all_new_orders.extend(orders)
            self.order_counter += len(orders)

            for o in orders:
                p.register_order(o.order_id)

        # 4. Process Cancellations
        for oid in all_cancels:
            self.book.cancel_order(oid)
            for p in self.participants:
                p.unregister_order(oid)

        # 5. Shuffle incoming orders to simulate microsecond latency
        if len(all_new_orders) > 1:
            self.rng.shuffle(all_new_orders)

        # 6. Execute Orders via Matching Engine
        tick_trades: List[Trade] = []
        for order in all_new_orders:
            trades = self.matching_engine.submit_order(order, timestamp=tick)
            if trades:
                tick_trades.extend(trades)
                for t in trades:
                    self.candle_aggregator.process_trade(t)
                    for p in self.participants:
                        p.on_trade(t)
                    # Hawkes self-excitation from executed volume
                    self.hawkes_excitation = min(3.5, self.hawkes_excitation + t.quantity * 0.005)

                    # Detect large trades for real-time event feed
                    if t.quantity >= 40.0:
                        sent = "bull" if t.is_buy_aggressor else "bear"
                        action = "Large Buy Order" if t.is_buy_aggressor else "Large Sell Order"
                        e = self._add_event(
                            category="order",
                            title=action,
                            detail=f"{t.quantity:.1f} units executed @ {t.price:.2f}",
                            sentiment=sent,
                        )
                        tick_events.append(e)

        # 7. Step Clock for Candle Aggregator (Check if candle timeframe closed)
        new_closed_candle = self.candle_aggregator.step_tick(tick)

        # 8. Record Price, Spread & Events
        active_price = self.book.last_trade_price
        self.price_history.append(active_price)
        if self.book.spread is not None:
            self.spread_history.append(self.book.spread)
            if self.book.spread >= 0.05:
                e = self._add_event(
                    category="spread",
                    title="Liquidity Thinning",
                    detail=f"Spread expanded to {self.book.spread:.2f} due to order flow",
                    sentiment="neutral",
                )
                tick_events.append(e)

        # 9. Update Higher-Level Structural Analytics on closed candle boundary
        if new_closed_candle is not None:
            candles = self.candle_aggregator.candles

            # Update Market Structure (Swings, BOS, CHoCH)
            self.market_structure.update(candles)

            # Register BSL/SSL pools at newly confirmed swings
            for sh in self.market_structure.swing_highs:
                if sh.candle_index not in self._registered_swing_high_indices:
                    self._registered_swing_high_indices.add(sh.candle_index)
                    pool_price = self.book.round(sh.price + self.book.tick_size)
                    self.latent_liquidity.register_pool(
                        LiquidityType.BSL, pool_price, volume=float(self.rng.uniform(60.0, 110.0)), tick=tick
                    )

            for sl in self.market_structure.swing_lows:
                if sl.candle_index not in self._registered_swing_low_indices:
                    self._registered_swing_low_indices.add(sl.candle_index)
                    pool_price = self.book.round(sl.price - self.book.tick_size)
                    self.latent_liquidity.register_pool(
                        LiquidityType.SSL, pool_price, volume=float(self.rng.uniform(60.0, 110.0)), tick=tick
                    )

            # Evaluate Liquidity Sweeps
            self.liquidity_detector.evaluate_sweeps(self.latent_liquidity.swept_pools, candles)

            # Update Fair Value Gaps
            self.fvg_detector.update(candles)

            # Check structural event notifications
            cur_bos = sum(1 for ev in self.market_structure.events if "BOS" in ev.event_type.value)
            cur_choch = sum(1 for ev in self.market_structure.events if "CHOCH" in ev.event_type.value)

            if cur_bos > self._last_bos_count:
                latest_ev = [ev for ev in self.market_structure.events if "BOS" in ev.event_type.value][-1]
                sent = "bull" if "BULLISH" in latest_ev.event_type.value else "bear"
                e = self._add_event(
                    category="structure",
                    title=latest_ev.event_type.value.replace("_", " "),
                    detail=latest_ev.description,
                    sentiment=sent,
                )
                tick_events.append(e)
                self._last_bos_count = cur_bos

            if cur_choch > self._last_choch_count:
                latest_ev = [ev for ev in self.market_structure.events if "CHOCH" in ev.event_type.value][-1]
                sent = "gold"
                e = self._add_event(
                    category="structure",
                    title="Change of Character (CHoCH)",
                    detail=latest_ev.description,
                    sentiment=sent,
                )
                tick_events.append(e)
                self._last_choch_count = cur_choch

            # Check FVG creation notifications
            if len(self.fvg_detector.fvgs) > self._last_fvg_count:
                newest_fvg = self.fvg_detector.fvgs[-1]
                sent = "bull" if newest_fvg.fvg_type.value == "bullish" else "bear"
                e = self._add_event(
                    category="fvg",
                    title=f"{newest_fvg.fvg_type.value.title()} FVG Formed",
                    detail=f"Gap from {newest_fvg.bottom_price:.2f} to {newest_fvg.top_price:.2f}",
                    sentiment=sent,
                )
                tick_events.append(e)
                self._last_fvg_count = len(self.fvg_detector.fvgs)

        # 10. Capture Snapshot & Tick Data
        tot_vol = self.matching_engine.total_trade_volume
        tot_delta = sum(c.delta for c in self.candle_aggregator.completed_candles)
        if self.candle_aggregator._current_candle:
            tot_delta += self.candle_aggregator._current_candle.delta

        tick_vol = sum(t.quantity for t in tick_trades)
        tick_buy_vol = sum(t.quantity for t in tick_trades if t.is_buy_aggressor)
        tick_sell_vol = sum(t.quantity for t in tick_trades if t.is_sell_aggressor)
        tick_del = tick_buy_vol - tick_sell_vol

        live_candle_dict = self.candle_aggregator.live_open_candle.to_dict() if self.candle_aggregator.live_open_candle else None

        snapshot = StepSnapshot(
            tick=tick,
            time_str=time_str,
            price=active_price,
            mid_price=self.book.mid_price,
            spread=self.book.spread,
            regime=regime.value,
            imbalance=self.book.imbalance,
            tick_volume=tick_vol,
            tick_delta=tick_del,
            tick_trades_count=len(tick_trades),
            recent_trades=[t.to_dict() for t in tick_trades[-5:]],
            completed_candles_count=len(self.candle_aggregator.completed_candles),
            live_open_candle=live_candle_dict,
            total_volume=tot_vol,
            total_delta=tot_delta,
            total_trades=self.matching_engine.trade_count,
            new_events=[ev.to_dict() for ev in tick_events],
        )
        self.snapshots.append(snapshot)

        # Store for Replay
        self.tick_history.append({
            "tick": tick,
            "time_str": time_str,
            "price": active_price,
            "mid_price": self.book.mid_price,
            "spread": self.book.spread,
            "tick_volume": tick_vol,
            "tick_delta": tick_del,
            "trade_count": len(tick_trades),
            "total_volume": tot_vol,
            "total_delta": tot_delta,
        })
        if len(self.tick_history) > 2000:
            self.tick_history.pop(0)

        return snapshot

    def run(self, total_ticks: Optional[int] = None) -> Dict[str, Any]:
        """Runs the simulation for the configured duration."""
        target_ticks = total_ticks or self.config.total_ticks
        while self.current_tick < target_ticks:
            self.step()

        self.candle_aggregator.finalize(self.current_tick)
        candles = self.candle_aggregator.completed_candles
        self.market_structure.update(candles)
        self.fvg_detector.update(candles)
        self.liquidity_detector.evaluate_sweeps(self.latent_liquidity.swept_pools, candles)

        return self.get_full_results()

    def get_full_results(self) -> Dict[str, Any]:
        """Gathers complete metrics, candles, structure, liquidity, FVGs, and event feed."""
        candles = self.candle_aggregator.candles
        trades = self.matching_engine.executed_trades
        stats = StatisticsEngine.compute(trades, self.candle_aggregator.completed_candles, self.spread_history)

        # Merge structural summaries
        stats.update(self.market_structure.get_summary())
        stats.update(self.fvg_detector.get_summary())
        stats.update(self.liquidity_detector.get_statistics(self.latent_liquidity.swept_pools))
        stats["current_regime"] = self.regime_manager.current_regime.value
        stats["current_time"] = self.current_time_str
        stats["current_tick"] = self.current_tick

        return {
            "config": {
                "initial_price": self.config.initial_price,
                "ticks_per_candle": self.config.ticks_per_candle,
                "tick_duration_seconds": self.config.tick_duration_seconds,
                "total_ticks": self.config.total_ticks,
                "seed": self.seed,
            },
            "clock": {
                "tick": self.current_tick,
                "time_str": self.current_time_str,
            },
            "statistics": stats,
            "candles": [c.to_dict() for c in candles],
            "live_open_candle": self.candle_aggregator.live_open_candle.to_dict() if self.candle_aggregator.live_open_candle else None,
            "swings": [s.to_dict() for s in self.market_structure.swings],
            "structure_events": [e.to_dict() for e in self.market_structure.events],
            "liquidity_pools": [p.to_dict() for p in self.latent_liquidity.pools],
            "fvgs": [f.to_dict() for f in self.fvg_detector.fvgs],
            "recent_events": [e.to_dict() for e in self.event_feed[-25:]],
            "order_book": {
                "mid_price": self.book.mid_price,
                "spread": self.book.spread,
                "best_bid": self.book.best_bid,
                "best_ask": self.book.best_ask,
                "bids": self.book.get_bid_depth(10),
                "asks": self.book.get_ask_depth(10),
            },
        }
