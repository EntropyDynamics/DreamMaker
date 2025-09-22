"""
Mock MetaTrader 5 module for testing without Wine.
Provides a complete simulation of MT5 API for development and testing.
"""

import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, NamedTuple
import numpy as np
import pandas as pd
from dataclasses import dataclass
from loguru import logger


# Mock MT5 constants
COPY_TICKS_ALL = 1
COPY_TICKS_INFO = 2
COPY_TICKS_TRADE = 3

TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_M15 = 15
TIMEFRAME_M30 = 30
TIMEFRAME_H1 = 60
TIMEFRAME_H4 = 240
TIMEFRAME_D1 = 1440


class MockTick(NamedTuple):
    """Mock tick structure matching MT5 tick"""
    time: int
    bid: float
    ask: float
    last: float
    volume_real: float
    time_msc: int
    flags: int


class MockSymbolInfo(NamedTuple):
    """Mock symbol info structure"""
    name: str
    description: str
    point: float
    digits: int
    spread: int
    trade_mode: int
    volume_min: float
    volume_max: float
    volume_step: float
    margin_initial: float
    margin_maintenance: float


class MockAccountInfo(NamedTuple):
    """Mock account info structure"""
    login: int
    trade_mode: int
    name: str
    server: str
    currency: str
    leverage: int
    profit: float
    equity: float
    balance: float
    margin: float
    margin_free: float
    margin_level: float


class MockMarketPrice:
    """Simulates realistic market price movements"""

    def __init__(self, initial_price: float = 1.1000, symbol: str = "EURUSD"):
        self.symbol = symbol
        self.base_price = initial_price
        self.current_price = initial_price
        self.last_time = time.time()
        self.volatility = 0.0001  # 1 pip volatility
        self.trend = 0.0
        self.spread_pips = 1.5

        # Symbol-specific settings
        if "JPY" in symbol:
            self.point = 0.001
            self.digits = 3
            self.spread_pips = 2.0
        else:
            self.point = 0.00001
            self.digits = 5

    def get_current_tick(self) -> MockTick:
        """Generate realistic tick data"""
        current_time = time.time()
        time_diff = current_time - self.last_time

        # Random walk with momentum
        random_change = np.random.normal(0, self.volatility * np.sqrt(time_diff))
        momentum = self.trend * time_diff

        self.current_price += random_change + momentum

        # Add some mean reversion
        mean_reversion = (self.base_price - self.current_price) * 0.001
        self.current_price += mean_reversion

        # Calculate bid/ask
        spread = self.spread_pips * self.point
        bid = self.current_price - spread / 2
        ask = self.current_price + spread / 2

        # Volume simulation
        volume = random.uniform(0.1, 5.0)

        # Flags simulation (bit flags for tick type)
        flags = random.choice([2, 4, 6])  # Different tick types

        self.last_time = current_time

        return MockTick(
            time=int(current_time),
            bid=round(bid, self.digits),
            ask=round(ask, self.digits),
            last=round(self.current_price, self.digits),
            volume_real=volume,
            time_msc=int(current_time * 1000),
            flags=flags
        )


class MockMT5:
    """Mock MetaTrader 5 API for testing"""

    def __init__(self):
        self.initialized = False
        self.connected = False
        self.selected_symbols = set()
        self.account_info = None
        self.last_error_code = 0
        self.last_error_description = ""

        # Price simulators for different symbols
        self.price_simulators = {
            "EURUSD": MockMarketPrice(1.1000, "EURUSD"),
            "GBPUSD": MockMarketPrice(1.3000, "GBPUSD"),
            "USDJPY": MockMarketPrice(110.00, "USDJPY"),
            "USDCHF": MockMarketPrice(0.9200, "USDCHF"),
            "AUDUSD": MockMarketPrice(0.7500, "AUDUSD"),
            "USDCAD": MockMarketPrice(1.2500, "USDCAD"),
            "NZDUSD": MockMarketPrice(0.7000, "NZDUSD"),
        }

        # Default symbol info
        self.symbol_infos = {
            symbol: MockSymbolInfo(
                name=symbol,
                description=f"{symbol} - Mock Symbol",
                point=sim.point,
                digits=sim.digits,
                spread=int(sim.spread_pips),
                trade_mode=0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                margin_initial=100.0,
                margin_maintenance=50.0
            )
            for symbol, sim in self.price_simulators.items()
        }

        logger.info("Mock MT5 module initialized")

    def initialize(self, path: str = "", login: int = 0, password: str = "",
                   server: str = "", timeout: int = 5000) -> bool:
        """Mock MT5 initialization"""
        logger.info(f"Mock MT5 initializing with login={login}, server={server}")

        # Simulate connection delay
        time.sleep(0.1)

        # Simulate occasional connection failures
        if random.random() < 0.05:  # 5% failure rate
            self.last_error_code = 10004
            self.last_error_description = "No connection to trade server"
            logger.warning("Mock MT5 connection failed (simulated)")
            return False

        self.initialized = True
        self.connected = True

        # Create mock account info
        self.account_info = MockAccountInfo(
            login=login or 12345678,
            trade_mode=0,
            name="Mock Account",
            server=server or "MockServer-Demo",
            currency="USD",
            leverage=100,
            profit=250.50,
            equity=10250.50,
            balance=10000.00,
            margin=0.00,
            margin_free=10250.50,
            margin_level=0.00
        )

        logger.info("Mock MT5 initialized successfully")
        return True

    def shutdown(self) -> None:
        """Mock MT5 shutdown"""
        logger.info("Mock MT5 shutting down")
        self.initialized = False
        self.connected = False
        self.selected_symbols.clear()

    def symbol_info(self, symbol: str) -> Optional[MockSymbolInfo]:
        """Get symbol information"""
        if not self.initialized:
            self.last_error_code = 10001
            self.last_error_description = "MetaTrader 5 not initialized"
            return None

        return self.symbol_infos.get(symbol)

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        """Select/deselect symbol"""
        if not self.initialized:
            self.last_error_code = 10001
            self.last_error_description = "MetaTrader 5 not initialized"
            return False

        if symbol not in self.symbol_infos:
            self.last_error_code = 4301
            self.last_error_description = f"Symbol {symbol} not found"
            return False

        if enable:
            self.selected_symbols.add(symbol)
            logger.debug(f"Symbol {symbol} selected")
        else:
            self.selected_symbols.discard(symbol)
            logger.debug(f"Symbol {symbol} deselected")

        return True

    def symbol_info_tick(self, symbol: str) -> Optional[MockTick]:
        """Get current tick for symbol"""
        if not self.initialized:
            self.last_error_code = 10001
            self.last_error_description = "MetaTrader 5 not initialized"
            return None

        if symbol not in self.selected_symbols:
            self.last_error_code = 4301
            self.last_error_description = f"Symbol {symbol} not selected"
            return None

        if symbol in self.price_simulators:
            return self.price_simulators[symbol].get_current_tick()

        return None

    def copy_ticks_from(self, symbol: str, date_from: datetime, count: int,
                        flags: int = COPY_TICKS_ALL) -> Optional[np.ndarray]:
        """Copy historical ticks"""
        if not self.initialized:
            self.last_error_code = 10001
            self.last_error_description = "MetaTrader 5 not initialized"
            return None

        if symbol not in self.symbol_infos:
            self.last_error_code = 4301
            self.last_error_description = f"Symbol {symbol} not found"
            return None

        # Generate historical ticks
        ticks = []
        current_time = date_from
        price_sim = self.price_simulators.get(symbol, MockMarketPrice())

        for i in range(count):
            # Go back in time
            tick_time = current_time - timedelta(seconds=i)
            timestamp = int(tick_time.timestamp())

            # Generate realistic historical tick
            tick = price_sim.get_current_tick()

            # Create numpy record
            tick_record = np.array([(
                timestamp,
                tick.bid,
                tick.ask,
                tick.last,
                tick.volume_real,
                timestamp * 1000,
                tick.flags
            )], dtype=[
                ('time', 'i8'),
                ('bid', 'f8'),
                ('ask', 'f8'),
                ('last', 'f8'),
                ('volume_real', 'f8'),
                ('time_msc', 'i8'),
                ('flags', 'i4')
            ])

            ticks.append(tick_record)

        # Reverse to get chronological order
        return np.concatenate(ticks[::-1])

    def account_info(self) -> Optional[MockAccountInfo]:
        """Get account information"""
        if not self.initialized:
            self.last_error_code = 10001
            self.last_error_description = "MetaTrader 5 not initialized"
            return None

        return self.account_info

    def last_error(self) -> tuple:
        """Get last error"""
        return (self.last_error_code, self.last_error_description)

    def version(self) -> tuple:
        """Get MT5 version"""
        return (500, 3000, "Mock MetaTrader 5")


# Global mock instance
_mock_mt5 = MockMT5()

# Mock functions that match MT5 API
def initialize(path: str = "", login: int = 0, password: str = "",
               server: str = "", timeout: int = 5000) -> bool:
    return _mock_mt5.initialize(path, login, password, server, timeout)

def shutdown() -> None:
    _mock_mt5.shutdown()

def symbol_info(symbol: str):
    return _mock_mt5.symbol_info(symbol)

def symbol_select(symbol: str, enable: bool = True) -> bool:
    return _mock_mt5.symbol_select(symbol, enable)

def symbol_info_tick(symbol: str):
    return _mock_mt5.symbol_info_tick(symbol)

def copy_ticks_from(symbol: str, date_from: datetime, count: int,
                    flags: int = COPY_TICKS_ALL):
    return _mock_mt5.copy_ticks_from(symbol, date_from, count, flags)

def account_info():
    return _mock_mt5.account_info()

def last_error() -> tuple:
    return _mock_mt5.last_error()

def version() -> tuple:
    return _mock_mt5.version()

# Additional mock functions for completeness
def terminal_info():
    """Mock terminal info"""
    return {
        'community_account': False,
        'community_connection': False,
        'connected': _mock_mt5.connected,
        'dlls_allowed': True,
        'trade_allowed': True,
        'tradeapi_disabled': False,
        'email_enabled': False,
        'ftp_enabled': False,
        'notifications_enabled': False,
        'mqid': False,
        'build': 3000,
        'maxbars': 65536,
        'codepage': 1252,
        'ping_last': 15,
        'community_balance': 0.0,
        'retransmission': 0.1,
        'company': 'MockBroker',
        'name': 'Mock MetaTrader 5',
        'language': 'English',
        'path': '/mock/mt5',
        'data_path': '/mock/mt5/data',
        'commondata_path': '/mock/mt5/common'
    }

def market_book_get(symbol: str):
    """Mock market book (depth of market)"""
    if symbol not in _mock_mt5.selected_symbols:
        return None

    # Generate mock market depth
    current_tick = _mock_mt5.symbol_info_tick(symbol)
    if not current_tick:
        return None

    book = []

    # Generate bid levels
    for i in range(5):
        price = current_tick.bid - i * _mock_mt5.symbol_infos[symbol].point
        volume = random.uniform(1.0, 10.0)
        book.append({
            'type': 1,  # Buy
            'price': price,
            'volume': volume,
            'volume_real': volume
        })

    # Generate ask levels
    for i in range(5):
        price = current_tick.ask + i * _mock_mt5.symbol_infos[symbol].point
        volume = random.uniform(1.0, 10.0)
        book.append({
            'type': 2,  # Sell
            'price': price,
            'volume': volume,
            'volume_real': volume
        })

    return book


# Simulate realistic market conditions
def simulate_market_event(symbol: str, event_type: str = "news"):
    """Simulate market events that affect price movement"""
    if symbol in _mock_mt5.price_simulators:
        sim = _mock_mt5.price_simulators[symbol]

        if event_type == "news":
            # High volatility spike
            sim.volatility *= random.uniform(2.0, 5.0)
            sim.trend = random.choice([-0.0005, 0.0005])
        elif event_type == "session_open":
            # Increased activity
            sim.volatility *= 1.5
        elif event_type == "session_close":
            # Decreased activity
            sim.volatility *= 0.5
            sim.trend *= 0.1


# Auto-simulate market events
def start_market_simulation():
    """Start background market simulation"""
    import threading

    def simulate():
        while _mock_mt5.initialized:
            time.sleep(random.uniform(30, 120))  # Random events

            if _mock_mt5.selected_symbols:
                symbol = random.choice(list(_mock_mt5.selected_symbols))
                event = random.choice(["news", "session_open", "session_close"])
                simulate_market_event(symbol, event)

    if _mock_mt5.initialized:
        thread = threading.Thread(target=simulate, daemon=True)
        thread.start()


# Module-level initialization
logger.info("Mock MT5 module loaded - Use for testing without Wine")