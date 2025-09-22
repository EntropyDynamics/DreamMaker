"""
Feature Engineering Agent - Transforms raw market data into predictive alphas.
Implements OFI, Micro-price, Hawkes processes, and fractional differentiation.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Deque
from collections import deque
from dataclasses import dataclass
import asyncio
from loguru import logger

from .base_agent import BaseAgent, Message, MessageType
from ..features.microstructure import (
    OrderFlowImbalance, MicroPrice, BookImbalance,
    SpreadMetrics, VolatilityFeatures, LiquidityMetrics
)
from ..features.hawkes_process import OrderFlowHawkes
from config.config import FeatureConfig


@dataclass
class FeatureSet:
    """Complete set of features at a point in time"""
    timestamp: pd.Timestamp

    # Price features
    mid_price: float
    micro_price: float
    weighted_mid_price: float

    # OFI features
    ofi_1: float
    ofi_2: float
    ofi_3: float
    ofi_5: float

    # Book imbalance
    book_imbalance: float
    weighted_imbalance: float
    book_pressure: float

    # Spread features
    spread: float
    relative_spread: float

    # Volatility features
    realized_volatility: float
    price_velocity: float
    price_acceleration: float

    # Hawkes intensities
    hawkes_buy_intensity: float
    hawkes_sell_intensity: float
    hawkes_buy_sell_ratio: float
    hawkes_self_excitation: float

    # Liquidity features
    kyle_lambda: float
    amihud_illiquidity: float

    # Fractionally differentiated features
    frac_diff_price: float
    frac_diff_volume: float

    # Technical indicators
    rsi: float
    macd_signal: float
    bollinger_position: float

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML models"""
        return np.array([
            self.mid_price, self.micro_price, self.weighted_mid_price,
            self.ofi_1, self.ofi_2, self.ofi_3, self.ofi_5,
            self.book_imbalance, self.weighted_imbalance, self.book_pressure,
            self.spread, self.relative_spread,
            self.realized_volatility, self.price_velocity, self.price_acceleration,
            self.hawkes_buy_intensity, self.hawkes_sell_intensity,
            self.hawkes_buy_sell_ratio, self.hawkes_self_excitation,
            self.kyle_lambda, self.amihud_illiquidity,
            self.frac_diff_price, self.frac_diff_volume,
            self.rsi, self.macd_signal, self.bollinger_position
        ])

    @staticmethod
    def get_feature_names() -> List[str]:
        """Get list of feature names"""
        return [
            "mid_price", "micro_price", "weighted_mid_price",
            "ofi_1", "ofi_2", "ofi_3", "ofi_5",
            "book_imbalance", "weighted_imbalance", "book_pressure",
            "spread", "relative_spread",
            "realized_volatility", "price_velocity", "price_acceleration",
            "hawkes_buy_intensity", "hawkes_sell_intensity",
            "hawkes_buy_sell_ratio", "hawkes_self_excitation",
            "kyle_lambda", "amihud_illiquidity",
            "frac_diff_price", "frac_diff_volume",
            "rsi", "macd_signal", "bollinger_position"
        ]


class FractionalDifferentiation:
    """
    Implements fractional differentiation for maintaining memory while achieving stationarity.
    Based on Marcos Lopez de Prado's research.
    """

    def __init__(self, d: float = 0.4, threshold: float = 1e-4):
        """
        Args:
            d: Differentiation order (0 < d < 1)
            threshold: Minimum weight threshold
        """
        self.d = d
        self.threshold = threshold
        self.weights = self._get_weights()

    def _get_weights(self, size: int = 100) -> np.ndarray:
        """Calculate fractional differentiation weights"""
        w = [1.0]
        for k in range(1, size):
            w_k = -w[-1] * (self.d - k + 1) / k
            if abs(w_k) < self.threshold:
                break
            w.append(w_k)
        return np.array(w[::-1])

    def transform(self, series: pd.Series) -> pd.Series:
        """Apply fractional differentiation to series"""
        if len(series) < len(self.weights):
            return pd.Series(index=series.index, dtype=float)

        # Apply weights using convolution
        result = np.convolve(series.values, self.weights, mode='valid')

        # Create output series with proper index
        output_index = series.index[len(self.weights)-1:]
        return pd.Series(result, index=output_index)


class TechnicalIndicators:
    """Calculate traditional technical indicators"""

    @staticmethod
    def rsi(prices: pd.Series, period: int = 14) -> float:
        """Relative Strength Index"""
        if len(prices) < period + 1:
            return 50.0

        deltas = prices.diff()
        gain = deltas.where(deltas > 0, 0).rolling(period).mean()
        loss = -deltas.where(deltas < 0, 0).rolling(period).mean()

        if loss.iloc[-1] == 0:
            return 100.0

        rs = gain.iloc[-1] / loss.iloc[-1]
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
        """MACD indicator"""
        if len(prices) < slow:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()

        return {
            "macd": macd_line.iloc[-1],
            "signal": signal_line.iloc[-1],
            "histogram": macd_line.iloc[-1] - signal_line.iloc[-1]
        }

    @staticmethod
    def bollinger_bands(prices: pd.Series, period: int = 20, std_dev: int = 2) -> Dict[str, float]:
        """Bollinger Bands"""
        if len(prices) < period:
            return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "position": 0.5}

        middle = prices.rolling(period).mean().iloc[-1]
        std = prices.rolling(period).std().iloc[-1]

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        current_price = prices.iloc[-1]

        # Position within bands (0 = at lower, 1 = at upper)
        if upper - lower > 0:
            position = (current_price - lower) / (upper - lower)
        else:
            position = 0.5

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "position": np.clip(position, 0, 1)
        }


class FeatureAgent(BaseAgent):
    """
    Agent responsible for feature engineering and alpha generation.
    Transforms raw market data into predictive features for ML models.
    """

    def __init__(self, config: FeatureConfig):
        super().__init__("FeatureAgent", "feature_engineer")
        self.config = config

        # Feature calculators
        self.ofi_calculator = OrderFlowImbalance(config.ofi_levels)
        self.volatility_tracker = VolatilityFeatures(config.volatility_window)
        self.hawkes_model = OrderFlowHawkes()
        self.frac_diff = FractionalDifferentiation(config.fractional_diff_d)

        # Data buffers
        self.price_buffer: Deque[float] = deque(maxlen=config.feature_window)
        self.volume_buffer: Deque[float] = deque(maxlen=config.feature_window)
        self.book_buffer: Deque[pd.DataFrame] = deque(maxlen=config.feature_window)
        self.feature_buffer: Deque[FeatureSet] = deque(maxlen=config.feature_window)

        # Price series for technical indicators
        self.price_series = pd.Series(dtype=float)
        self.volume_series = pd.Series(dtype=float)

        # Statistics
        self.stats = {
            "features_calculated": 0,
            "invalid_features": 0,
            "hawkes_updates": 0,
            "features_sent": 0
        }

    async def initialize(self) -> None:
        """Initialize feature engineering components"""
        logger.info("Initializing Feature Agent")

        # Start feature calculation task
        asyncio.create_task(self._process_features())

    async def process(self, message: Message) -> Optional[Message]:
        """Process incoming market data and generate features"""

        if message.type == MessageType.DATA:
            data_type = message.payload.get("data_type")

            if data_type == "tick":
                await self._process_tick(message.payload["tick"])

            elif data_type == "book":
                await self._process_book(message.payload["book"])

            elif data_type == "bar":
                await self._process_bar(message.payload["bar"])

        elif message.type == MessageType.COMMAND:
            command = message.payload.get("command")

            if command == "get_latest_features":
                if self.feature_buffer:
                    return Message(
                        sender=self.id,
                        receiver=message.sender,
                        type=MessageType.DATA,
                        payload={"features": self.feature_buffer[-1]},
                        correlation_id=message.id
                    )

            elif command == "get_feature_history":
                return Message(
                    sender=self.id,
                    receiver=message.sender,
                    type=MessageType.DATA,
                    payload={"feature_history": list(self.feature_buffer)},
                    correlation_id=message.id
                )

        return None

    async def cleanup(self) -> None:
        """Cleanup feature engineering resources"""
        logger.info("Cleaning up Feature Agent")

    async def _process_tick(self, tick: Any) -> None:
        """Process incoming tick data"""
        # Update price and volume buffers
        if hasattr(tick, 'last') and hasattr(tick, 'volume'):
            self.price_buffer.append(tick.last)
            self.volume_buffer.append(tick.volume)

            # Update volatility tracker
            self.volatility_tracker.update(tick.last)

            # Update price series for technical indicators
            self.price_series = pd.concat([
                self.price_series,
                pd.Series([tick.last], index=[tick.time])
            ]).tail(self.config.feature_window)

            self.volume_series = pd.concat([
                self.volume_series,
                pd.Series([tick.volume], index=[tick.time])
            ]).tail(self.config.feature_window)

    async def _process_book(self, book: Any) -> None:
        """Process incoming order book data"""
        # Convert book to DataFrame format expected by feature calculators
        book_df = self._book_to_dataframe(book)
        self.book_buffer.append(book_df)

        # Calculate features if we have enough data
        if len(self.book_buffer) >= 2:
            features = await self._calculate_features(book)
            if features:
                self.feature_buffer.append(features)
                self.stats["features_calculated"] += 1

                # Broadcast features to ML agents
                await self._broadcast_features(features)

    async def _process_bar(self, bar: Dict) -> None:
        """Process constructed bar data"""
        # Update Hawkes model with bar data if available
        if "tick_count" in bar:
            # Simplified: use tick count as proxy for order arrivals
            self.hawkes_model.hawkes.events[0].append(pd.Timestamp.now().timestamp())
            self.stats["hawkes_updates"] += 1

    async def _calculate_features(self, book: Any) -> Optional[FeatureSet]:
        """Calculate all features from current market state"""
        try:
            timestamp = book.timestamp if hasattr(book, 'timestamp') else pd.Timestamp.now()

            # Price features
            mid_price = book.mid_price if hasattr(book, 'mid_price') else 0
            micro_price = book.micro_price if hasattr(book, 'micro_price') else 0

            # Calculate weighted mid price
            if hasattr(book, 'best_bid') and hasattr(book, 'best_ask'):
                weighted_mid = MicroPrice.volume_weighted(
                    book.best_bid, book.best_ask,
                    book.bid_levels[0].volume if book.bid_levels else 0,
                    book.ask_levels[0].volume if book.ask_levels else 0
                )
            else:
                weighted_mid = mid_price

            # OFI calculation
            book_df = self.book_buffer[-1] if self.book_buffer else pd.DataFrame()
            ofi_values = self.ofi_calculator.calculate(book_df)

            # Book imbalance
            bid_vol = book.bid_levels[0].volume if hasattr(book, 'bid_levels') and book.bid_levels else 0
            ask_vol = book.ask_levels[0].volume if hasattr(book, 'ask_levels') and book.ask_levels else 0
            book_imbalance = BookImbalance.simple_imbalance(bid_vol, ask_vol)
            weighted_imbalance = BookImbalance.weighted_imbalance(book_df) if not book_df.empty else 0
            book_pressure = BookImbalance.book_pressure(book_df) if not book_df.empty else 0

            # Spread features
            spread = book.spread if hasattr(book, 'spread') else 0
            relative_spread = SpreadMetrics.relative_spread(
                book.best_bid if hasattr(book, 'best_bid') else 0,
                book.best_ask if hasattr(book, 'best_ask') else 0
            )

            # Volatility features
            realized_vol = self.volatility_tracker.realized_volatility()
            price_velocity = self.volatility_tracker.price_velocity()
            price_acceleration = self.volatility_tracker.price_acceleration()

            # Hawkes features
            hawkes_features = self.hawkes_model.get_excitation_features(timestamp.timestamp())

            # Liquidity features
            if len(self.price_buffer) > 1 and len(self.volume_buffer) > 1:
                returns = np.diff(list(self.price_buffer)) / list(self.price_buffer)[:-1]
                kyle_lambda = LiquidityMetrics.kyle_lambda(
                    abs(returns[-1]) if len(returns) > 0 else 0,
                    self.volume_buffer[-1]
                )
                amihud = LiquidityMetrics.amihud_illiquidity(
                    list(returns), list(self.volume_buffer)[1:]
                )
            else:
                kyle_lambda = 0
                amihud = 0

            # Fractional differentiation
            if len(self.price_series) > 20:
                frac_diff_price = self.frac_diff.transform(self.price_series).iloc[-1] if len(self.price_series) > 0 else 0
                frac_diff_volume = self.frac_diff.transform(self.volume_series).iloc[-1] if len(self.volume_series) > 0 else 0
            else:
                frac_diff_price = 0
                frac_diff_volume = 0

            # Technical indicators
            rsi = TechnicalIndicators.rsi(self.price_series) if len(self.price_series) > 14 else 50
            macd_dict = TechnicalIndicators.macd(self.price_series) if len(self.price_series) > 26 else {"signal": 0}
            bollinger = TechnicalIndicators.bollinger_bands(self.price_series) if len(self.price_series) > 20 else {"position": 0.5}

            # Create feature set
            features = FeatureSet(
                timestamp=timestamp,
                mid_price=mid_price,
                micro_price=micro_price,
                weighted_mid_price=weighted_mid,
                ofi_1=ofi_values.get(1, 0),
                ofi_2=ofi_values.get(2, 0),
                ofi_3=ofi_values.get(3, 0),
                ofi_5=ofi_values.get(5, 0),
                book_imbalance=book_imbalance,
                weighted_imbalance=weighted_imbalance,
                book_pressure=book_pressure,
                spread=spread,
                relative_spread=relative_spread,
                realized_volatility=realized_vol,
                price_velocity=price_velocity,
                price_acceleration=price_acceleration,
                hawkes_buy_intensity=hawkes_features.get("hawkes_intensity_market_buy", 0) +
                                    hawkes_features.get("hawkes_intensity_limit_buy", 0),
                hawkes_sell_intensity=hawkes_features.get("hawkes_intensity_market_sell", 0) +
                                     hawkes_features.get("hawkes_intensity_limit_sell", 0),
                hawkes_buy_sell_ratio=hawkes_features.get("hawkes_buy_sell_ratio", 0.5),
                hawkes_self_excitation=hawkes_features.get("hawkes_self_excitation", 0),
                kyle_lambda=kyle_lambda,
                amihud_illiquidity=amihud,
                frac_diff_price=frac_diff_price,
                frac_diff_volume=frac_diff_volume,
                rsi=rsi,
                macd_signal=macd_dict.get("signal", 0),
                bollinger_position=bollinger.get("position", 0.5)
            )

            return features

        except Exception as e:
            logger.error(f"Error calculating features: {e}")
            self.stats["invalid_features"] += 1
            return None

    async def _broadcast_features(self, features: FeatureSet) -> None:
        """Broadcast features to ML agents"""
        message = Message(
            sender=self.id,
            type=MessageType.DATA,
            payload={
                "data_type": "features",
                "features": features,
                "timestamp": features.timestamp
            }
        )
        self.send_message(message)
        self.stats["features_sent"] += 1

    async def _process_features(self) -> None:
        """Background task to process features continuously"""
        while self.state.value == "running":
            try:
                # Process any pending calculations
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Error in feature processing: {e}")

    def _book_to_dataframe(self, book: Any) -> pd.DataFrame:
        """Convert book object to DataFrame format"""
        data = {}

        # Add bid levels
        if hasattr(book, 'bid_levels'):
            for i, level in enumerate(book.bid_levels[:5], 1):
                data[f'bid_price_{i}'] = [level.price]
                data[f'bid_size_{i}'] = [level.volume]

        # Add ask levels
        if hasattr(book, 'ask_levels'):
            for i, level in enumerate(book.ask_levels[:5], 1):
                data[f'ask_price_{i}'] = [level.price]
                data[f'ask_size_{i}'] = [level.volume]

        return pd.DataFrame(data)

    def get_feature_statistics(self) -> Dict[str, Any]:
        """Get feature engineering statistics"""
        base_stats = self.get_status()

        # Calculate feature statistics
        if self.feature_buffer:
            features_array = np.array([f.to_array() for f in self.feature_buffer])
            feature_names = FeatureSet.get_feature_names()

            feature_stats = {}
            for i, name in enumerate(feature_names):
                values = features_array[:, i]
                feature_stats[name] = {
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values)),
                    "min": float(np.min(values)),
                    "max": float(np.max(values))
                }
        else:
            feature_stats = {}

        base_stats.update({
            "feature_stats": self.stats,
            "buffer_sizes": {
                "price": len(self.price_buffer),
                "volume": len(self.volume_buffer),
                "book": len(self.book_buffer),
                "features": len(self.feature_buffer)
            },
            "feature_statistics": feature_stats
        })

        return base_stats