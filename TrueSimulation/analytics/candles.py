"""
Candle aggregator that constructs OHLCV, volume delta, and volume-at-price
from discrete simulated trades and ticks.
Maintains a continuously updating active open candle across multi-tick intervals.
"""

from typing import List, Dict, Optional
from market.trade import Trade
from analytics.candle import Candle


def format_sim_time(tick_seconds: int, base_seconds: int = 9 * 3600 + 30 * 60) -> str:
    """Formats simulation tick (in seconds) to HH:MM:SS format starting at 09:30:00."""
    total_sec = (base_seconds + tick_seconds) % 86400
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class CandleAggregator:
    """
    Aggregates executed trades into OHLCV candles based on simulation ticks.

    Key capabilities:
    - Accurate multi-second tick-to-candle boundary management (e.g. 60s per candle).
    - Current open candle remains active and updates OHLC continuously in real time.
    - Zero-volume periods preserve price continuation (O=H=L=C=prev_close).
    - Tracks buy volume, sell volume, order flow delta, and volume-at-price profiles.
    """

    def __init__(self, ticks_per_candle: int = 60, initial_price: float = 100.0):
        self.ticks_per_candle = max(1, ticks_per_candle)
        self.last_price = initial_price
        self.completed_candles: List[Candle] = []
        self.session_volume_at_price: Dict[float, float] = {}

        # In-progress candle state
        self._current_index = 0
        self._candle_start_tick = 0
        self._trades_in_current = 0

        # Initialize the active open candle immediately at the start price
        self._current_candle: Candle = Candle(
            index=self._current_index,
            open=self.last_price,
            high=self.last_price,
            low=self.last_price,
            close=self.last_price,
            volume=0.0,
            buy_volume=0.0,
            sell_volume=0.0,
            delta=0.0,
            trade_count=0,
            start_tick=0,
            end_tick=0,
            time_str=format_sim_time(0),
        )

    @property
    def candles(self) -> List[Candle]:
        """All closed candles plus a live snapshot of the current active candle."""
        result = list(self.completed_candles)
        if self._current_candle is not None:
            result.append(self._current_candle)
        return result

    @property
    def live_open_candle(self) -> Optional[Candle]:
        """The currently forming unfinished candle."""
        return self._current_candle

    def get_completed_candles(self) -> List[Candle]:
        return self.completed_candles

    def process_trade(self, trade: Trade) -> None:
        """Updates the active live candle with an executed trade."""
        price = trade.price
        qty = trade.quantity
        self.last_price = price

        c = self._current_candle
        if c is None:
            c = Candle(
                index=self._current_index,
                open=price,
                high=price,
                low=price,
                close=price,
                start_tick=self._candle_start_tick,
                end_tick=trade.timestamp,
                time_str=format_sim_time(self._candle_start_tick),
            )
            self._current_candle = c

        # For the very first trade of the entire simulation session (candle 0), anchor open to first trade price
        if self._current_index == 0 and self._trades_in_current == 0 and c.volume <= 1e-9:
            c.open = price
            c.high = price
            c.low = price
            c.close = price
        else:
            c.high = max(c.high, price)
            c.low = min(c.low, price)
            c.close = price

        c.volume += qty
        c.trade_count += 1
        c.end_tick = trade.timestamp

        if trade.is_buy_aggressor:
            c.buy_volume += qty
        else:
            c.sell_volume += qty
        c.delta = c.buy_volume - c.sell_volume

        # Volume-at-price profiling
        c.volume_at_price[price] = c.volume_at_price.get(price, 0.0) + qty
        self.session_volume_at_price[price] = self.session_volume_at_price.get(price, 0.0) + qty
        self._trades_in_current += 1

    def step_tick(self, current_tick: int) -> Optional[Candle]:
        """
        Advances the simulation clock by one tick (e.g. 1 second).
        If the candle duration has elapsed (e.g. 60 seconds), closes the current candle
        and opens a fresh new one.
        Returns the finalized Candle if a candle closed on this tick, else None.
        """
        closed_candle = None

        if self._current_candle is not None:
            self._current_candle.end_tick = current_tick
            self._current_candle.close = self.last_price

        # Check if candle duration window has expired
        if (current_tick - self._candle_start_tick) >= self.ticks_per_candle:
            # Finalize and close active candle
            c = self._current_candle
            c.end_tick = current_tick - 1
            self.completed_candles.append(c)
            closed_candle = c

            # Initialize brand new open candle at boundary
            self._current_index += 1
            self._candle_start_tick = current_tick
            self._trades_in_current = 0
            self._current_candle = Candle(
                index=self._current_index,
                open=self.last_price,
                high=self.last_price,
                low=self.last_price,
                close=self.last_price,
                volume=0.0,
                buy_volume=0.0,
                sell_volume=0.0,
                delta=0.0,
                trade_count=0,
                start_tick=current_tick,
                end_tick=current_tick,
                time_str=format_sim_time(current_tick),
            )

        return closed_candle

    def finalize(self, final_tick: int) -> Optional[Candle]:
        """Finalizes any partially formed candle at the end of the simulation."""
        if self._current_candle is not None:
            self._current_candle.end_tick = final_tick
            self.completed_candles.append(self._current_candle)
            c = self._current_candle
            self._current_candle = None
            return c
        return None
