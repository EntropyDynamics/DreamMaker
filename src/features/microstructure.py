"""
Microstructure Feature Engineering Module.
Implements Order Flow Imbalance (OFI), Micro-price, and other LOB-based features.
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from collections import deque
from scipy import stats
import warnings
warnings.filterwarnings('ignore')


@dataclass
class MicrostructureFeatures:
    """Container for all microstructure features"""
    timestamp: pd.Timestamp

    # Price features
    mid_price: float
    micro_price: float
    weighted_mid_price: float

    # Spread features
    spread: float
    relative_spread: float
    effective_spread: float

    # Order flow features
    ofi: Dict[int, float]  # OFI at different levels
    trade_flow_imbalance: float
    volume_order_imbalance: float

    # Book imbalance features
    book_imbalance: float
    book_pressure: float
    book_skew: float

    # Depth features
    bid_depth: List[float]
    ask_depth: List[float]
    total_depth: float
    depth_imbalance: float

    # Volatility features
    realized_volatility: float
    price_velocity: float
    price_acceleration: float

    # Additional features
    kyle_lambda: float
    amihud_illiquidity: float
    realized_spread: float


class OrderFlowImbalance:
    """
    Calculate Order Flow Imbalance (OFI) following Cont et al. (2014).
    OFI measures the net order flow at different price levels.
    """

    def __init__(self, levels: List[int] = [1, 2, 3, 5]):
        """
        Args:
            levels: List of book levels to calculate OFI for
        """
        self.levels = levels
        self.prev_book_state = None

    def calculate(self, book: pd.DataFrame) -> Dict[int, float]:
        """
        Calculate OFI for current book state.

        OFI(n) = Σ(ΔBid_i - ΔAsk_i) for i=1 to n
        where Δ represents change from previous state

        Args:
            book: DataFrame with columns ['bid_price_i', 'bid_size_i', 'ask_price_i', 'ask_size_i']

        Returns:
            Dictionary mapping level to OFI value
        """
        ofi_values = {}

        if self.prev_book_state is None:
            # First observation, set all OFI to 0
            for level in self.levels:
                ofi_values[level] = 0.0
            self.prev_book_state = book.copy()
            return ofi_values

        for n in self.levels:
            ofi = 0.0
            for i in range(1, min(n + 1, len(book) + 1)):
                # Calculate bid side changes
                bid_col = f'bid_size_{i}'
                ask_col = f'ask_size_{i}'

                if bid_col in book.columns and bid_col in self.prev_book_state.columns:
                    # Check if price level exists in both states
                    curr_bid_price = book[f'bid_price_{i}'].iloc[0] if f'bid_price_{i}' in book.columns else 0
                    prev_bid_price = self.prev_book_state[f'bid_price_{i}'].iloc[0] if f'bid_price_{i}' in self.prev_book_state.columns else 0

                    if curr_bid_price == prev_bid_price:
                        # Same price level, calculate volume change
                        delta_bid = book[bid_col].iloc[0] - self.prev_book_state[bid_col].iloc[0]
                    else:
                        # Price level changed, treat as new volume
                        delta_bid = book[bid_col].iloc[0]
                else:
                    delta_bid = 0.0

                # Calculate ask side changes
                if ask_col in book.columns and ask_col in self.prev_book_state.columns:
                    curr_ask_price = book[f'ask_price_{i}'].iloc[0] if f'ask_price_{i}' in book.columns else 0
                    prev_ask_price = self.prev_book_state[f'ask_price_{i}'].iloc[0] if f'ask_price_{i}' in self.prev_book_state.columns else 0

                    if curr_ask_price == prev_ask_price:
                        delta_ask = book[ask_col].iloc[0] - self.prev_book_state[ask_col].iloc[0]
                    else:
                        delta_ask = book[ask_col].iloc[0]
                else:
                    delta_ask = 0.0

                ofi += delta_bid - delta_ask

            ofi_values[n] = ofi

        self.prev_book_state = book.copy()
        return ofi_values


class MicroPrice:
    """
    Calculate various micro-price estimates that improve upon the simple mid-price.
    """

    @staticmethod
    def volume_weighted(bid_price: float, ask_price: float,
                       bid_volume: float, ask_volume: float) -> float:
        """
        Volume-weighted micro price.

        MP = (bid * ask_volume + ask * bid_volume) / (bid_volume + ask_volume)
        """
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return (bid_price + ask_price) / 2

        return (bid_price * ask_volume + ask_price * bid_volume) / total_volume

    @staticmethod
    def depth_weighted(book: pd.DataFrame, levels: int = 5) -> float:
        """
        Depth-weighted micro price using multiple levels.
        """
        weighted_bid = 0.0
        weighted_ask = 0.0
        total_bid_volume = 0.0
        total_ask_volume = 0.0

        for i in range(1, min(levels + 1, len(book) + 1)):
            bid_price_col = f'bid_price_{i}'
            bid_size_col = f'bid_size_{i}'
            ask_price_col = f'ask_price_{i}'
            ask_size_col = f'ask_size_{i}'

            if bid_price_col in book.columns:
                price = book[bid_price_col].iloc[0]
                volume = book[bid_size_col].iloc[0]
                weighted_bid += price * volume
                total_bid_volume += volume

            if ask_price_col in book.columns:
                price = book[ask_price_col].iloc[0]
                volume = book[ask_size_col].iloc[0]
                weighted_ask += price * volume
                total_ask_volume += volume

        if total_bid_volume == 0 or total_ask_volume == 0:
            return (book['bid_price_1'].iloc[0] + book['ask_price_1'].iloc[0]) / 2

        avg_bid = weighted_bid / total_bid_volume
        avg_ask = weighted_ask / total_ask_volume

        return (avg_bid * total_ask_volume + avg_ask * total_bid_volume) / (total_bid_volume + total_ask_volume)

    @staticmethod
    def imbalance_adjusted(bid_price: float, ask_price: float,
                          bid_volume: float, ask_volume: float,
                          trade_price: Optional[float] = None) -> float:
        """
        Micro price adjusted for order imbalance and recent trades.
        """
        base_micro = MicroPrice.volume_weighted(bid_price, ask_price, bid_volume, ask_volume)

        if trade_price is not None:
            # Adjust based on trade direction
            if abs(trade_price - bid_price) < abs(trade_price - ask_price):
                # Trade was likely a sell
                adjustment = -0.01 * (ask_volume - bid_volume) / (ask_volume + bid_volume)
            else:
                # Trade was likely a buy
                adjustment = 0.01 * (bid_volume - ask_volume) / (ask_volume + bid_volume)

            base_micro += adjustment * (ask_price - bid_price)

        return base_micro


class BookImbalance:
    """
    Calculate various book imbalance metrics.
    """

    @staticmethod
    def simple_imbalance(bid_volume: float, ask_volume: float) -> float:
        """
        Simple volume imbalance: (bid_vol - ask_vol) / (bid_vol + ask_vol)
        Returns value between -1 and 1.
        """
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        return (bid_volume - ask_volume) / total

    @staticmethod
    def weighted_imbalance(book: pd.DataFrame, levels: int = 5,
                          decay_factor: float = 0.5) -> float:
        """
        Weighted book imbalance with exponential decay by level.
        """
        weighted_bid = 0.0
        weighted_ask = 0.0

        for i in range(1, min(levels + 1, len(book) + 1)):
            weight = decay_factor ** (i - 1)

            bid_size_col = f'bid_size_{i}'
            ask_size_col = f'ask_size_{i}'

            if bid_size_col in book.columns:
                weighted_bid += weight * book[bid_size_col].iloc[0]

            if ask_size_col in book.columns:
                weighted_ask += weight * book[ask_size_col].iloc[0]

        total = weighted_bid + weighted_ask
        if total == 0:
            return 0.0

        return (weighted_bid - weighted_ask) / total

    @staticmethod
    def book_pressure(book: pd.DataFrame, levels: int = 5) -> float:
        """
        Book pressure metric: measures buying vs selling pressure.
        """
        bid_pressure = 0.0
        ask_pressure = 0.0

        best_bid = book['bid_price_1'].iloc[0] if 'bid_price_1' in book.columns else 0
        best_ask = book['ask_price_1'].iloc[0] if 'ask_price_1' in book.columns else 0

        if best_bid == 0 or best_ask == 0:
            return 0.0

        mid_price = (best_bid + best_ask) / 2

        for i in range(1, min(levels + 1, len(book) + 1)):
            bid_price_col = f'bid_price_{i}'
            bid_size_col = f'bid_size_{i}'
            ask_price_col = f'ask_price_{i}'
            ask_size_col = f'ask_size_{i}'

            if bid_price_col in book.columns:
                price = book[bid_price_col].iloc[0]
                volume = book[bid_size_col].iloc[0]
                distance = abs(mid_price - price)
                if distance > 0:
                    bid_pressure += volume / distance

            if ask_price_col in book.columns:
                price = book[ask_price_col].iloc[0]
                volume = book[ask_size_col].iloc[0]
                distance = abs(mid_price - price)
                if distance > 0:
                    ask_pressure += volume / distance

        total_pressure = bid_pressure + ask_pressure
        if total_pressure == 0:
            return 0.0

        return (bid_pressure - ask_pressure) / total_pressure


class SpreadMetrics:
    """
    Calculate various spread-based metrics.
    """

    @staticmethod
    def absolute_spread(bid: float, ask: float) -> float:
        """Absolute spread in price units."""
        return ask - bid

    @staticmethod
    def relative_spread(bid: float, ask: float) -> float:
        """Relative spread as percentage of mid price."""
        mid = (bid + ask) / 2
        if mid == 0:
            return 0.0
        return (ask - bid) / mid

    @staticmethod
    def effective_spread(trade_price: float, mid_price: float,
                        trade_direction: int) -> float:
        """
        Effective spread: 2 * direction * (trade_price - mid_price)
        direction: 1 for buy, -1 for sell
        """
        return 2 * trade_direction * (trade_price - mid_price)

    @staticmethod
    def realized_spread(trade_price: float, future_mid_price: float,
                        trade_direction: int) -> float:
        """
        Realized spread: 2 * direction * (trade_price - future_mid_price)
        Measures actual cost after price impact dissipates.
        """
        return 2 * trade_direction * (trade_price - future_mid_price)


class VolatilityFeatures:
    """
    Calculate volatility and related features.
    """

    def __init__(self, window: int = 20):
        self.window = window
        self.price_history = deque(maxlen=window)
        self.return_history = deque(maxlen=window)

    def update(self, price: float) -> None:
        """Update price history."""
        if len(self.price_history) > 0:
            ret = np.log(price / self.price_history[-1])
            self.return_history.append(ret)
        self.price_history.append(price)

    def realized_volatility(self) -> float:
        """Calculate realized volatility from returns."""
        if len(self.return_history) < 2:
            return 0.0
        return np.std(self.return_history) * np.sqrt(252 * 390 * 60)  # Annualized

    def price_velocity(self) -> float:
        """Rate of price change (first derivative)."""
        if len(self.price_history) < 2:
            return 0.0
        return self.price_history[-1] - self.price_history[-2]

    def price_acceleration(self) -> float:
        """Rate of velocity change (second derivative)."""
        if len(self.price_history) < 3:
            return 0.0
        v1 = self.price_history[-1] - self.price_history[-2]
        v2 = self.price_history[-2] - self.price_history[-3]
        return v1 - v2

    def garman_klass_volatility(self, high: float, low: float,
                               close: float, open_: float) -> float:
        """
        Garman-Klass volatility estimator using OHLC data.
        More efficient than close-to-close volatility.
        """
        if open_ == 0 or close == 0:
            return 0.0

        hl_component = 0.5 * (np.log(high / low)) ** 2
        co_component = (2 * np.log(2) - 1) * (np.log(close / open_)) ** 2

        return np.sqrt(hl_component - co_component) * np.sqrt(252 * 390 * 60)


class LiquidityMetrics:
    """
    Calculate liquidity-related metrics.
    """

    @staticmethod
    def kyle_lambda(price_impact: float, volume: float) -> float:
        """
        Kyle's lambda: measures price impact per unit volume.
        λ = Δprice / Δvolume
        """
        if volume == 0:
            return 0.0
        return price_impact / volume

    @staticmethod
    def amihud_illiquidity(returns: List[float], volumes: List[float]) -> float:
        """
        Amihud illiquidity measure: average of |return| / volume.
        Higher values indicate lower liquidity.
        """
        if len(returns) != len(volumes) or len(returns) == 0:
            return 0.0

        illiquidity_values = []
        for ret, vol in zip(returns, volumes):
            if vol > 0:
                illiquidity_values.append(abs(ret) / vol)

        if not illiquidity_values:
            return 0.0

        return np.mean(illiquidity_values)

    @staticmethod
    def roll_measure(prices: List[float]) -> float:
        """
        Roll's measure: estimates effective spread from price changes.
        Based on serial covariance of price changes.
        """
        if len(prices) < 3:
            return 0.0

        price_changes = np.diff(prices)
        if len(price_changes) < 2:
            return 0.0

        cov = np.cov(price_changes[:-1], price_changes[1:])[0, 1]

        if cov >= 0:
            return 0.0  # Model assumptions violated

        return 2 * np.sqrt(-cov)