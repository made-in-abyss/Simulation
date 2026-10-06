"""
Base interface for simulated market participants.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from market.order import Order
from market.regimes import RegimeProfile


class Participant(ABC):
    """
    Abstract base class for all market agents.
    """

    def __init__(self, trader_id: str):
        self.trader_id = trader_id
        self.active_order_ids: List[int] = []

    def register_order(self, order_id: int) -> None:
        self.active_order_ids.append(order_id)

    def unregister_order(self, order_id: int) -> None:
        if order_id in self.active_order_ids:
            self.active_order_ids.remove(order_id)

    def on_trade(self, trade) -> None:
        """Callback when an executed trade occurs involving this participant."""
        pass

    @abstractmethod
    def generate_actions(
        self,
        order_book,
        regime_profile: RegimeProfile,
        rng: np.random.Generator,
        tick: int,
        order_id_counter: int,
        recent_prices: List[float],
    ) -> Tuple[List[int], List[Order]]:
        """
        Generates actions for the current simulation step.

        Returns:
            A tuple of:
            - List of existing order_ids to cancel.
            - List of new Order objects to submit.
        """
        pass
