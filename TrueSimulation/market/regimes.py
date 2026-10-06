"""
Market Regimes and probabilistic state transitions.
Regimes remain hidden from standard market observers but drive underlying
participant aggression, liquidity thickness, volatility, and order persistence.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


class MarketRegime(str, Enum):
    """Hidden market regimes."""
    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility_expansion"
    LOW_VOLATILITY = "low_volatility_compression"
    LIQUIDITY_DROUGHT = "liquidity_drought"


@dataclass
class RegimeProfile:
    """
    Behavioral parameter modulations applied under a specific regime.
    """
    regime: MarketRegime
    directional_drift: float        # Positive -> buyer advantage, Negative -> seller advantage
    momentum_sensitivity: float    # How strongly momentum traders react
    mean_reversion_strength: float # How strongly mean-reversion traders push back
    volatility_mult: float         # Multiplier on order sizes and price dispersion
    mm_spread_ticks: int           # Target spread in ticks for Market Makers
    mm_depth_mult: float           # Multiplier on MM resting depth
    large_order_prob: float        # Probability per tick of institutional block order
    noise_activity: float          # Frequency of noise retail orders


DEFAULT_REGIME_PROFILES: Dict[MarketRegime, RegimeProfile] = {
    MarketRegime.TRENDING_BULLISH: RegimeProfile(
        regime=MarketRegime.TRENDING_BULLISH,
        directional_drift=0.40,
        momentum_sensitivity=1.6,
        mean_reversion_strength=0.5,
        volatility_mult=1.2,
        mm_spread_ticks=2,
        mm_depth_mult=1.0,
        large_order_prob=0.08,
        noise_activity=1.0,
    ),
    MarketRegime.TRENDING_BEARISH: RegimeProfile(
        regime=MarketRegime.TRENDING_BEARISH,
        directional_drift=-0.40,
        momentum_sensitivity=1.6,
        mean_reversion_strength=0.5,
        volatility_mult=1.3,
        mm_spread_ticks=2,
        mm_depth_mult=0.9,
        large_order_prob=0.09,
        noise_activity=1.0,
    ),
    MarketRegime.RANGE: RegimeProfile(
        regime=MarketRegime.RANGE,
        directional_drift=0.0,
        momentum_sensitivity=0.6,
        mean_reversion_strength=1.8,
        volatility_mult=0.8,
        mm_spread_ticks=1,
        mm_depth_mult=1.4,
        large_order_prob=0.03,
        noise_activity=0.9,
    ),
    MarketRegime.HIGH_VOLATILITY: RegimeProfile(
        regime=MarketRegime.HIGH_VOLATILITY,
        directional_drift=0.0,
        momentum_sensitivity=1.8,
        mean_reversion_strength=0.8,
        volatility_mult=2.4,
        mm_spread_ticks=5,
        mm_depth_mult=0.5,
        large_order_prob=0.14,
        noise_activity=1.4,
    ),
    MarketRegime.LOW_VOLATILITY: RegimeProfile(
        regime=MarketRegime.LOW_VOLATILITY,
        directional_drift=0.0,
        momentum_sensitivity=0.4,
        mean_reversion_strength=1.2,
        volatility_mult=0.4,
        mm_spread_ticks=1,
        mm_depth_mult=1.8,
        large_order_prob=0.01,
        noise_activity=0.6,
    ),
    MarketRegime.LIQUIDITY_DROUGHT: RegimeProfile(
        regime=MarketRegime.LIQUIDITY_DROUGHT,
        directional_drift=0.0,
        momentum_sensitivity=1.1,
        mean_reversion_strength=0.4,
        volatility_mult=1.6,
        mm_spread_ticks=6,
        mm_depth_mult=0.25,
        large_order_prob=0.06,
        noise_activity=0.4,
    ),
}


class RegimeManager:
    """
    Manages the stochastic evolution of market regimes using a Markov transition matrix.
    Transitions happen naturally with a tunable persistence horizon.
    """

    def __init__(
        self,
        initial_regime: MarketRegime = MarketRegime.RANGE,
        transition_probability: float = 0.015,
        profiles: Optional[Dict[MarketRegime, RegimeProfile]] = None,
        seed: Optional[int] = None,
    ):
        self.current_regime = initial_regime
        self.transition_prob = transition_probability
        self.profiles = profiles or DEFAULT_REGIME_PROFILES
        self.rng = np.random.default_rng(seed)
        self.ticks_in_regime = 0
        self.regime_history: List[MarketRegime] = [initial_regime]

        # Transition matrix biased towards staying in the current regime
        self.regimes_list = list(MarketRegime)
        self._build_transition_matrix()

    def _build_transition_matrix(self) -> None:
        n = len(self.regimes_list)
        p_stay = 1.0 - self.transition_prob
        p_leave = self.transition_prob / (n - 1)

        self.transition_matrix = np.full((n, n), p_leave)
        for i in range(n):
            self.transition_matrix[i, i] = p_stay

    @property
    def current_profile(self) -> RegimeProfile:
        return self.profiles[self.current_regime]

    def step(self) -> MarketRegime:
        """
        Steps the Markov chain for one tick.
        """
        self.ticks_in_regime += 1
        curr_idx = self.regimes_list.index(self.current_regime)

        if self.rng.random() < self.transition_prob:
            # Transition to a new regime
            probs = self.transition_matrix[curr_idx].copy()
            probs[curr_idx] = 0.0
            probs = probs / np.sum(probs)
            new_idx = self.rng.choice(len(self.regimes_list), p=probs)
            self.current_regime = self.regimes_list[new_idx]
            self.ticks_in_regime = 0

        self.regime_history.append(self.current_regime)
        return self.current_regime

    def set_regime(self, regime: MarketRegime) -> None:
        """Manual regime override for testing or scenario analysis."""
        self.current_regime = regime
        self.ticks_in_regime = 0
