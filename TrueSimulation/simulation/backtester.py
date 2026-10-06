"""
Backtesting API allowing custom trading strategies to trade against the live simulated market.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from market.order import Order, OrderType, Side
from analytics.candle import Candle


class Strategy(ABC):
    """
    Abstract trading strategy interface for the Market Simulator.
    """

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name
        self.position: float = 0.0
        self.cash: float = 100000.0
        self.entry_price: float = 0.0
        self.realized_pnl: float = 0.0
        self.trade_history: List[Dict[str, Any]] = []

    def on_tick(self, snapshot, engine) -> None:
        """Called on every simulation tick."""
        pass

    def on_candle(self, candle: Candle, engine) -> None:
        """Called whenever a candle closes."""
        pass

    def buy_market(self, engine, quantity: float) -> None:
        """Sends an aggressive market buy order."""
        if quantity <= 0:
            return
        order = Order(
            order_id=engine.order_counter + 1,
            trader_id=self.name,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=quantity,
            timestamp=engine.current_tick,
        )
        engine.order_counter += 1
        trades = engine.matching_engine.submit_order(order, timestamp=engine.current_tick)
        for t in trades:
            cost = t.price * t.quantity
            self.cash -= cost
            self.position += t.quantity
            self.entry_price = t.price
            self.trade_history.append({"side": "BUY", "price": t.price, "qty": t.quantity, "tick": t.timestamp})

    def sell_market(self, engine, quantity: float) -> None:
        """Sends an aggressive market sell order."""
        if quantity <= 0:
            return
        order = Order(
            order_id=engine.order_counter + 1,
            trader_id=self.name,
            side=Side.SELL,
            order_type=OrderType.MARKET,
            price=None,
            quantity=quantity,
            timestamp=engine.current_tick,
        )
        engine.order_counter += 1
        trades = engine.matching_engine.submit_order(order, timestamp=engine.current_tick)
        for t in trades:
            proceeds = t.price * t.quantity
            self.cash += proceeds
            if self.position > 0:
                pnl = (t.price - self.entry_price) * t.quantity
                self.realized_pnl += pnl
            self.position -= t.quantity
            self.trade_history.append({"side": "SELL", "price": t.price, "qty": t.quantity, "tick": t.timestamp})

    def get_equity(self, current_price: float) -> float:
        return self.cash + (self.position * current_price)


class BacktestEngine:
    """
    Executes a Strategy on top of the SimulationEngine.
    """

    def __init__(self, simulation_engine, strategy: Strategy):
        self.engine = simulation_engine
        self.strategy = strategy
        self.equity_curve: List[float] = []

    def run(self, total_ticks: Optional[int] = None) -> Dict[str, Any]:
        target = total_ticks or self.engine.config.total_ticks
        init_equity = self.strategy.get_equity(self.engine.book.last_trade_price)

        last_candle_count = 0

        while self.engine.current_tick < target:
            snap = self.engine.step()

            # Strategy tick hook
            self.strategy.on_tick(snap, self.engine)

            # Strategy candle hook
            cur_candles = len(self.engine.candle_aggregator.completed_candles)
            if cur_candles > last_candle_count:
                last_c = self.engine.candle_aggregator.completed_candles[-1]
                self.strategy.on_candle(last_c, self.engine)
                last_candle_count = cur_candles

            curr_equity = self.strategy.get_equity(self.engine.book.last_trade_price)
            self.equity_curve.append(curr_equity)

        final_equity = self.strategy.get_equity(self.engine.book.last_trade_price)
        total_pnl = final_equity - init_equity
        ret_pct = (total_pnl / init_equity) * 100.0 if init_equity > 0 else 0.0

        return {
            "strategy": self.strategy.name,
            "initial_equity": round(init_equity, 2),
            "final_equity": round(final_equity, 2),
            "total_pnl": round(total_pnl, 2),
            "return_pct": round(ret_pct, 2),
            "realized_pnl": round(self.strategy.realized_pnl, 2),
            "total_trades": len(self.strategy.trade_history),
            "final_position": round(self.strategy.position, 2),
        }
