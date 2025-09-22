"""
Unit tests for microstructure features.
Tests OFI, micro-price, and book imbalance calculations.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime

from src.features.microstructure import (
    OrderFlowImbalance,
    MicroPrice,
    BookImbalance,
    SpreadMetrics,
    VolatilityFeatures,
    LiquidityMetrics
)


class TestOrderFlowImbalance:
    """Test Order Flow Imbalance calculations"""

    def test_ofi_initialization(self):
        """Test OFI calculator initialization"""
        ofi = OrderFlowImbalance(levels=[1, 2, 3])
        assert ofi.levels == [1, 2, 3]
        assert ofi.prev_book_state is None

    def test_ofi_first_calculation(self):
        """Test OFI returns zeros on first calculation"""
        ofi = OrderFlowImbalance(levels=[1, 2])

        # Create sample book
        book = pd.DataFrame({
            'bid_price_1': [100.0],
            'bid_size_1': [10.0],
            'ask_price_1': [101.0],
            'ask_size_1': [15.0],
            'bid_price_2': [99.0],
            'bid_size_2': [20.0],
            'ask_price_2': [102.0],
            'ask_size_2': [25.0]
        })

        result = ofi.calculate(book)
        assert result[1] == 0.0
        assert result[2] == 0.0

    def test_ofi_calculation_with_changes(self):
        """Test OFI calculation with volume changes"""
        ofi = OrderFlowImbalance(levels=[1])

        # First book state
        book1 = pd.DataFrame({
            'bid_price_1': [100.0],
            'bid_size_1': [10.0],
            'ask_price_1': [101.0],
            'ask_size_1': [15.0]
        })

        # Initialize with first state
        ofi.calculate(book1)

        # Second book state with increased bid, decreased ask
        book2 = pd.DataFrame({
            'bid_price_1': [100.0],  # Same price
            'bid_size_1': [20.0],    # Increased by 10
            'ask_price_1': [101.0],  # Same price
            'ask_size_1': [10.0]     # Decreased by 5
        })

        result = ofi.calculate(book2)

        # OFI = ΔBid - ΔAsk = 10 - (-5) = 15
        assert result[1] == 15.0

    def test_ofi_with_price_level_changes(self):
        """Test OFI when price levels change"""
        ofi = OrderFlowImbalance(levels=[1])

        book1 = pd.DataFrame({
            'bid_price_1': [100.0],
            'bid_size_1': [10.0],
            'ask_price_1': [101.0],
            'ask_size_1': [15.0]
        })

        ofi.calculate(book1)

        # Price levels change
        book2 = pd.DataFrame({
            'bid_price_1': [100.5],  # Different price
            'bid_size_1': [20.0],
            'ask_price_1': [101.5],  # Different price
            'ask_size_1': [10.0]
        })

        result = ofi.calculate(book2)

        # When prices change, treat as new volume
        assert result[1] == 10.0  # 20 - 10


class TestMicroPrice:
    """Test micro-price calculations"""

    def test_volume_weighted_micro_price(self):
        """Test volume-weighted micro price"""
        bid_price = 100.0
        ask_price = 101.0
        bid_volume = 10.0
        ask_volume = 20.0

        micro_price = MicroPrice.volume_weighted(
            bid_price, ask_price, bid_volume, ask_volume
        )

        # MP = (100 * 20 + 101 * 10) / (10 + 20) = 3010 / 30 = 100.333...
        expected = (bid_price * ask_volume + ask_price * bid_volume) / (bid_volume + ask_volume)
        assert abs(micro_price - expected) < 0.001

    def test_volume_weighted_with_zero_volume(self):
        """Test micro price with zero volume"""
        micro_price = MicroPrice.volume_weighted(100.0, 101.0, 0.0, 0.0)
        assert micro_price == 100.5  # Falls back to mid price

    def test_depth_weighted_micro_price(self):
        """Test depth-weighted micro price"""
        book = pd.DataFrame({
            'bid_price_1': [100.0],
            'bid_size_1': [10.0],
            'ask_price_1': [101.0],
            'ask_size_1': [15.0],
            'bid_price_2': [99.5],
            'bid_size_2': [20.0],
            'ask_price_2': [101.5],
            'ask_size_2': [25.0]
        })

        micro_price = MicroPrice.depth_weighted(book, levels=2)
        assert isinstance(micro_price, float)
        assert 99.0 < micro_price < 102.0  # Should be within reasonable range

    def test_imbalance_adjusted_micro_price(self):
        """Test imbalance-adjusted micro price"""
        bid_price = 100.0
        ask_price = 101.0
        bid_volume = 30.0  # More bid volume
        ask_volume = 10.0
        trade_price = 100.2  # Trade closer to bid (sell)

        micro_price = MicroPrice.imbalance_adjusted(
            bid_price, ask_price, bid_volume, ask_volume, trade_price
        )

        # Should adjust downward due to sell trade
        base_micro = MicroPrice.volume_weighted(bid_price, ask_price, bid_volume, ask_volume)
        assert micro_price < base_micro


class TestBookImbalance:
    """Test book imbalance metrics"""

    def test_simple_imbalance(self):
        """Test simple volume imbalance"""
        imbalance = BookImbalance.simple_imbalance(30.0, 10.0)
        assert imbalance == 0.5  # (30-10)/(30+10) = 20/40 = 0.5

        imbalance = BookImbalance.simple_imbalance(10.0, 30.0)
        assert imbalance == -0.5  # (10-30)/(10+30) = -20/40 = -0.5

        imbalance = BookImbalance.simple_imbalance(20.0, 20.0)
        assert imbalance == 0.0  # Equal volumes

    def test_simple_imbalance_zero_volume(self):
        """Test imbalance with zero total volume"""
        imbalance = BookImbalance.simple_imbalance(0.0, 0.0)
        assert imbalance == 0.0

    def test_weighted_imbalance(self):
        """Test weighted book imbalance"""
        book = pd.DataFrame({
            'bid_size_1': [10.0],
            'ask_size_1': [15.0],
            'bid_size_2': [20.0],
            'ask_size_2': [25.0]
        })

        imbalance = BookImbalance.weighted_imbalance(book, levels=2, decay_factor=0.5)

        # Level 1: weight=1.0, bid=10, ask=15
        # Level 2: weight=0.5, bid=20*0.5=10, ask=25*0.5=12.5
        # Total: bid=20, ask=27.5
        # Imbalance = (20-27.5)/(20+27.5) = -7.5/47.5
        expected = -7.5 / 47.5
        assert abs(imbalance - expected) < 0.01

    def test_book_pressure(self):
        """Test book pressure metric"""
        book = pd.DataFrame({
            'bid_price_1': [100.0],
            'bid_size_1': [10.0],
            'ask_price_1': [101.0],
            'ask_size_1': [15.0],
            'bid_price_2': [99.5],
            'bid_size_2': [20.0],
            'ask_price_2': [101.5],
            'ask_size_2': [25.0]
        })

        pressure = BookImbalance.book_pressure(book, levels=2)
        assert isinstance(pressure, float)
        assert -1.0 <= pressure <= 1.0  # Should be normalized


class TestSpreadMetrics:
    """Test spread calculations"""

    def test_absolute_spread(self):
        """Test absolute spread calculation"""
        spread = SpreadMetrics.absolute_spread(100.0, 101.0)
        assert spread == 1.0

    def test_relative_spread(self):
        """Test relative spread calculation"""
        spread = SpreadMetrics.relative_spread(100.0, 101.0)
        # (101-100)/100.5 = 1/100.5 ≈ 0.00995
        expected = 1.0 / 100.5
        assert abs(spread - expected) < 0.0001

    def test_relative_spread_zero_mid(self):
        """Test relative spread with zero mid price"""
        spread = SpreadMetrics.relative_spread(0.0, 0.0)
        assert spread == 0.0

    def test_effective_spread(self):
        """Test effective spread calculation"""
        trade_price = 100.8
        mid_price = 100.5

        # Buy trade
        spread = SpreadMetrics.effective_spread(trade_price, mid_price, 1)
        assert spread == 2 * (100.8 - 100.5)  # 0.6

        # Sell trade
        spread = SpreadMetrics.effective_spread(trade_price, mid_price, -1)
        assert spread == -2 * (100.8 - 100.5)  # -0.6

    def test_realized_spread(self):
        """Test realized spread calculation"""
        trade_price = 100.8
        future_mid = 100.6

        spread = SpreadMetrics.realized_spread(trade_price, future_mid, 1)
        assert spread == 2 * (100.8 - 100.6)  # 0.4


class TestVolatilityFeatures:
    """Test volatility feature calculations"""

    def test_volatility_initialization(self):
        """Test volatility tracker initialization"""
        vol = VolatilityFeatures(window=10)
        assert vol.window == 10
        assert len(vol.price_history) == 0

    def test_price_updates(self):
        """Test price history updates"""
        vol = VolatilityFeatures(window=3)

        vol.update(100.0)
        vol.update(101.0)
        vol.update(99.0)

        assert len(vol.price_history) == 3
        assert list(vol.price_history) == [100.0, 101.0, 99.0]

    def test_realized_volatility(self):
        """Test realized volatility calculation"""
        vol = VolatilityFeatures(window=5)

        # Add price series with known volatility
        prices = [100.0, 101.0, 99.5, 100.5, 99.0]
        for price in prices:
            vol.update(price)

        volatility = vol.realized_volatility()
        assert isinstance(volatility, float)
        assert volatility > 0

    def test_price_velocity(self):
        """Test price velocity (first derivative)"""
        vol = VolatilityFeatures()

        vol.update(100.0)
        vol.update(102.0)

        velocity = vol.price_velocity()
        assert velocity == 2.0  # 102 - 100

    def test_price_acceleration(self):
        """Test price acceleration (second derivative)"""
        vol = VolatilityFeatures()

        vol.update(100.0)
        vol.update(102.0)  # velocity = 2
        vol.update(103.0)  # velocity = 1

        acceleration = vol.price_acceleration()
        assert acceleration == -1.0  # 1 - 2


class TestLiquidityMetrics:
    """Test liquidity metric calculations"""

    def test_kyle_lambda(self):
        """Test Kyle's lambda calculation"""
        price_impact = 0.5
        volume = 100.0

        lambda_val = LiquidityMetrics.kyle_lambda(price_impact, volume)
        assert lambda_val == 0.005  # 0.5 / 100

    def test_kyle_lambda_zero_volume(self):
        """Test Kyle's lambda with zero volume"""
        lambda_val = LiquidityMetrics.kyle_lambda(0.5, 0.0)
        assert lambda_val == 0.0

    def test_amihud_illiquidity(self):
        """Test Amihud illiquidity measure"""
        returns = [0.01, -0.02, 0.015, -0.005]
        volumes = [100.0, 150.0, 80.0, 120.0]

        illiquidity = LiquidityMetrics.amihud_illiquidity(returns, volumes)

        # Calculate expected
        expected = np.mean([
            abs(0.01) / 100,
            abs(-0.02) / 150,
            abs(0.015) / 80,
            abs(-0.005) / 120
        ])

        assert abs(illiquidity - expected) < 0.0001

    def test_roll_measure(self):
        """Test Roll's spread measure"""
        prices = [100.0, 100.2, 99.8, 100.1, 99.9]

        roll = LiquidityMetrics.roll_measure(prices)
        assert isinstance(roll, float)
        assert roll >= 0  # Should be non-negative when valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])