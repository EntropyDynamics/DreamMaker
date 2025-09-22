"""
Mock MetaTrader5 module for testing without Wine/MT5 installation.
Simulates MT5 API for development and testing purposes.
"""

import random
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np


# MT5 Constants
COPY_TICKS_ALL = 1
COPY_TICKS_INFO = 2
COPY_TICKS_TRADE = 3
TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_H1 = 60


@dataclass
class MockSymbolInfo:
    """Mock symbol information"""
    name: str
    bid: float
    ask: float
    digits: int
    point: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float

    @property
    def spread(self):
        return int((self.ask - self.bid) / self.point)


@dataclass
class MockTick:
    """Mock tick data"""
    time: int
    bid: float
    ask: float
    last: float
    volume: float
    time_msc: int
    flags: int
    volume_real: float


@dataclass
class MockAccountInfo:
    """Mock account information"""
    login: int
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    leverage: int
    currency: str
    server: str


class MockMT5:
    """Mock MetaTrader5 module for testing"""

    def __init__(self):
        self.initialized = False
        self.last_error_code = 0
        self.last_error_description = ""
        self.selected_symbol = None
        self.account = None

        # Simulated market data
        self.base_price = 5000.0
        self.volatility = 0.0002
        self.tick_counter = 0

    def initialize(self, path: str = None, login: int = None,
                   password: str = None, server: str = None,
                   timeout: int = 60000, portable: bool = False) -> bool:
        """Mock MT5 initialization"""
        self.initialized = True
        self.account = MockAccountInfo(
            login=login or 12345,
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            margin_free=10000.0,
            margin_level=0.0,
            leverage=100,
            currency="USD",
            server=server or "MockServer"
        )
        return True

    def shutdown(self):
        """Mock MT5 shutdown"""
        self.initialized = False
        self.selected_symbol = None

    def last_error(self) -> Tuple[int, str]:
        """Return last error"""
        return (self.last_error_code, self.last_error_description)

    def symbol_info(self, symbol: str) -> Optional[MockSymbolInfo]:
        """Get symbol information"""
        if not self.initialized:
            self.last_error_code = -1
            self.last_error_description = "Not initialized"
            return None

        # Generate mock symbol info
        spread = random.uniform(0.5, 2.0)
        bid = self.base_price + random.uniform(-10, 10)

        return MockSymbolInfo(
            name=symbol,
            bid=bid,
            ask=bid + spread,
            digits=2,
            point=0.01,
            trade_contract_size=1.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01
        )

    def symbol_info_tick(self, symbol: str) -> Optional[MockTick]:
        """Get latest tick for symbol"""
        if not self.initialized:
            return None

        # Generate realistic tick data with random walk
        self.tick_counter += 1
        self.base_price += random.gauss(0, self.base_price * self.volatility)

        spread = random.uniform(0.5, 2.0)
        bid = self.base_price
        ask = bid + spread
        last = bid if random.random() < 0.5 else ask

        current_time = int(time.time())

        return MockTick(
            time=current_time,
            bid=bid,
            ask=ask,
            last=last,
            volume=random.uniform(0.1, 10.0),
            time_msc=current_time * 1000 + random.randint(0, 999),
            flags=random.choice([0, 1, 2, 4]),
            volume_real=random.uniform(0.1, 10.0)
        )

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        """Select symbol for trading"""
        if not self.initialized:
            return False

        if enable:
            self.selected_symbol = symbol
        else:
            self.selected_symbol = None

        return True

    def copy_ticks_from(self, symbol: str, date_from: datetime,
                        count: int, flags: int) -> Optional[np.ndarray]:
        """Get historical ticks"""
        if not self.initialized:
            return None

        # Generate mock historical ticks
        ticks = []
        current_time = int(date_from.timestamp())
        price = self.base_price

        for i in range(count):
            # Random walk for price
            price += random.gauss(0, price * self.volatility)
            spread = random.uniform(0.5, 2.0)
            bid = price
            ask = bid + spread
            last = bid if random.random() < 0.5 else ask

            tick_time = current_time - (count - i) * random.randint(1, 5)

            tick_data = (
                tick_time,  # time
                bid,        # bid
                ask,        # ask
                last,       # last
                random.uniform(0.1, 10.0),  # volume
                tick_time * 1000,  # time_msc
                random.choice([0, 1, 2, 4]),  # flags
                random.uniform(0.1, 10.0)  # volume_real
            )
            ticks.append(tick_data)

        # Create structured array matching MT5 format
        dtype = [
            ('time', 'i8'), ('bid', 'f8'), ('ask', 'f8'), ('last', 'f8'),
            ('volume', 'u8'), ('time_msc', 'i8'), ('flags', 'u4'), ('volume_real', 'f8')
        ]

        return np.array(ticks, dtype=dtype)

    def copy_rates_from(self, symbol: str, timeframe: int,
                        date_from: datetime, count: int) -> Optional[np.ndarray]:
        """Get historical OHLC data"""
        if not self.initialized:
            return None

        # Generate mock OHLC data
        rates = []
        current_time = int(date_from.timestamp())
        price = self.base_price

        for i in range(count):
            # Generate OHLC for each bar
            open_price = price
            high = price + random.uniform(0, 10)
            low = price - random.uniform(0, 10)
            close = random.uniform(low, high)
            price = close  # Next bar opens at previous close

            bar_time = current_time - (count - i) * timeframe * 60

            bar_data = (
                bar_time,  # time
                open_price,  # open
                high,  # high
                low,  # low
                close,  # close
                random.randint(100, 10000),  # tick_volume
                0,  # spread
                random.uniform(1000, 100000)  # real_volume
            )
            rates.append(bar_data)

        # Create structured array matching MT5 format
        dtype = [
            ('time', 'i8'), ('open', 'f8'), ('high', 'f8'), ('low', 'f8'),
            ('close', 'f8'), ('tick_volume', 'u8'), ('spread', 'i4'), ('real_volume', 'f8')
        ]

        return np.array(rates, dtype=dtype)

    def account_info(self) -> Optional[MockAccountInfo]:
        """Get account information"""
        if not self.initialized:
            return None
        return self.account

    def positions_get(self, symbol: str = None) -> List:
        """Get open positions"""
        if not self.initialized:
            return []
        # Return empty list for now (no positions)
        return []

    def orders_get(self, symbol: str = None) -> List:
        """Get pending orders"""
        if not self.initialized:
            return []
        # Return empty list for now (no orders)
        return []


# Create module-level instance to mimic MT5 module behavior
_mock_instance = MockMT5()

# Export functions that mimic MT5 module interface
initialize = _mock_instance.initialize
shutdown = _mock_instance.shutdown
last_error = _mock_instance.last_error
symbol_info = _mock_instance.symbol_info
symbol_info_tick = _mock_instance.symbol_info_tick
symbol_select = _mock_instance.symbol_select
copy_ticks_from = _mock_instance.copy_ticks_from
copy_rates_from = _mock_instance.copy_rates_from
account_info = _mock_instance.account_info
positions_get = _mock_instance.positions_get
orders_get = _mock_instance.orders_get