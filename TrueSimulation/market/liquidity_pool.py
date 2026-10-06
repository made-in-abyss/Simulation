"""
Liquidity Pools and Latent Stop / Liquidation Order Management.
Distinguishes between visible resting limit book liquidity and latent
stop clusters residing above swing highs (BSL) and below swing lows (SSL).
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import numpy as np

from market.order import Order, OrderType, Side
from market.order_book import OrderBook


class LiquidityType(str, Enum):
    BSL = "BSL"  # Buy-side liquidity (stops above highs)
    SSL = "SSL"  # Sell-side liquidity (stops below lows)


@dataclass
class LiquidityPool:
    """
    Represents an identified liquidity pool.
    """
    pool_id: int
    pool_type: LiquidityType
    price: float
    estimated_volume: float
    created_tick: int
    is_swept: bool = False
    swept_tick: Optional[int] = None
    swept_price: Optional[float] = None
    outcome: Optional[str] = None  # "reversal" or "continuation"

    def to_dict(self) -> dict:
        return {
            "pool_id": self.pool_id,
            "type": self.pool_type.value,
            "price": self.price,
            "estimated_volume": round(self.estimated_volume, 1),
            "created_tick": self.created_tick,
            "is_swept": self.is_swept,
            "swept_tick": self.swept_tick,
            "swept_price": self.swept_price,
            "outcome": self.outcome,
        }


class LatentLiquidityManager:
    """
    Manages latent stop-loss and breakout liquidity clusters.
    When price trades through a pool, latent orders trigger into real market orders.
    """

    def __init__(self, book: OrderBook):
        self.book = book
        self.pools: List[LiquidityPool] = []
        self._pool_counter = 0

    def register_pool(
        self,
        pool_type: LiquidityType,
        price: float,
        volume: float,
        tick: int,
    ) -> LiquidityPool:
        """Registers a new latent liquidity level (e.g. above a new high or below a low)."""
        self._pool_counter += 1
        rounded_p = self.book.round(price)
        pool = LiquidityPool(
            pool_id=self._pool_counter,
            pool_type=pool_type,
            price=rounded_p,
            estimated_volume=volume,
            created_tick=tick,
        )
        self.pools.append(pool)
        return pool

    def check_triggers(
        self,
        current_price: float,
        tick: int,
        order_id_counter: int,
        rng: np.random.Generator,
    ) -> Tuple[List[Order], List[LiquidityPool]]:
        """
        Checks whether current_price has swept through any active pools.
        If swept, generates market orders representing triggered stops/liquidations.
        """
        triggered_orders: List[Order] = []
        swept_pools: List[LiquidityPool] = []
        cur_oid = order_id_counter

        for pool in self.pools:
            if pool.is_swept:
                continue

            # BSL trigger: price rises to or above pool price
            if pool.pool_type == LiquidityType.BSL and current_price >= pool.price:
                pool.is_swept = True
                pool.swept_tick = tick
                pool.swept_price = current_price
                swept_pools.append(pool)

                # Stop buys triggered by buyers/short-covers (realistic cluster size)
                stop_qty = round(min(55.0, pool.estimated_volume * 0.45) * rng.uniform(0.8, 1.2), 1)
                cur_oid += 1
                triggered_orders.append(
                    Order(
                        order_id=cur_oid,
                        trader_id="STOP_RUN_BSL",
                        side=Side.BUY,
                        order_type=OrderType.MARKET,
                        price=None,
                        quantity=stop_qty,
                        timestamp=tick,
                    )
                )

            # SSL trigger: price drops to or below pool price
            elif pool.pool_type == LiquidityType.SSL and current_price <= pool.price:
                pool.is_swept = True
                pool.swept_tick = tick
                pool.swept_price = current_price
                swept_pools.append(pool)

                # Stop sells triggered by long stop-outs/breakout sellers (realistic cluster size)
                stop_qty = round(min(55.0, pool.estimated_volume * 0.45) * rng.uniform(0.8, 1.2), 1)
                cur_oid += 1
                triggered_orders.append(
                    Order(
                        order_id=cur_oid,
                        trader_id="STOP_RUN_SSL",
                        side=Side.SELL,
                        order_type=OrderType.MARKET,
                        price=None,
                        quantity=stop_qty,
                        timestamp=tick,
                    )
                )

        return triggered_orders, swept_pools

    @property
    def active_bsl_pools(self) -> List[LiquidityPool]:
        return [p for p in self.pools if not p.is_swept and p.pool_type == LiquidityType.BSL]

    @property
    def active_ssl_pools(self) -> List[LiquidityPool]:
        return [p for p in self.pools if not p.is_swept and p.pool_type == LiquidityType.SSL]

    @property
    def swept_pools(self) -> List[LiquidityPool]:
        return [p for p in self.pools if p.is_swept]
