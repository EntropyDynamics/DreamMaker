"""
Bridge module to handle MT5 connection via Wine or mock for testing.
Automatically detects environment and uses appropriate backend.
"""

import os
import sys
import platform
from typing import Optional
from loguru import logger


def get_mt5_module():
    """
    Get appropriate MT5 module based on environment.
    Returns mock MT5 in WSL/Linux without Wine, real MT5 otherwise.
    """

    # Check if we're in testing mode
    if os.getenv('USE_MOCK_MT5', '').lower() == 'true':
        logger.info("Using mock MT5 module (USE_MOCK_MT5=true)")
        from src.utils.mock_mt5 import (
            initialize, shutdown, last_error, symbol_info,
            symbol_info_tick, symbol_select, copy_ticks_from,
            copy_rates_from, account_info, positions_get, orders_get,
            COPY_TICKS_ALL, COPY_TICKS_INFO, COPY_TICKS_TRADE,
            TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_H1
        )

        class MockMT5Module:
            """Wrapper to provide module-like interface"""
            def __init__(self):
                self.initialize = initialize
                self.shutdown = shutdown
                self.last_error = last_error
                self.symbol_info = symbol_info
                self.symbol_info_tick = symbol_info_tick
                self.symbol_select = symbol_select
                self.copy_ticks_from = copy_ticks_from
                self.copy_rates_from = copy_rates_from
                self.account_info = account_info
                self.positions_get = positions_get
                self.orders_get = orders_get
                self.COPY_TICKS_ALL = COPY_TICKS_ALL
                self.COPY_TICKS_INFO = COPY_TICKS_INFO
                self.COPY_TICKS_TRADE = COPY_TICKS_TRADE
                self.TIMEFRAME_M1 = TIMEFRAME_M1
                self.TIMEFRAME_M5 = TIMEFRAME_M5
                self.TIMEFRAME_H1 = TIMEFRAME_H1

        return MockMT5Module()

    # Check if running on Windows
    if platform.system() == 'Windows':
        try:
            import MetaTrader5 as mt5
            logger.info("Using real MetaTrader5 module (Windows)")
            return mt5
        except ImportError as e:
            logger.error(f"Failed to import MetaTrader5 on Windows: {e}")
            logger.info("Falling back to mock MT5 module")
            from src.utils.mock_mt5 import (
                initialize, shutdown, last_error, symbol_info,
                symbol_info_tick, symbol_select, copy_ticks_from,
                copy_rates_from, account_info, positions_get, orders_get,
                COPY_TICKS_ALL, COPY_TICKS_INFO, COPY_TICKS_TRADE,
                TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_H1
            )

            class MockMT5Module:
                def __init__(self):
                    self.initialize = initialize
                    self.shutdown = shutdown
                    self.last_error = last_error
                    self.symbol_info = symbol_info
                    self.symbol_info_tick = symbol_info_tick
                    self.symbol_select = symbol_select
                    self.copy_ticks_from = copy_ticks_from
                    self.copy_rates_from = copy_rates_from
                    self.account_info = account_info
                    self.positions_get = positions_get
                    self.orders_get = orders_get
                    self.COPY_TICKS_ALL = COPY_TICKS_ALL
                    self.COPY_TICKS_INFO = COPY_TICKS_INFO
                    self.COPY_TICKS_TRADE = COPY_TICKS_TRADE
                    self.TIMEFRAME_M1 = TIMEFRAME_M1
                    self.TIMEFRAME_M5 = TIMEFRAME_M5
                    self.TIMEFRAME_H1 = TIMEFRAME_H1

            return MockMT5Module()

    # Check if Wine is available for Linux/WSL
    if platform.system() == 'Linux':
        wine_available = os.system('which wine > /dev/null 2>&1') == 0

        if wine_available and os.getenv('USE_WINE_MT5', '').lower() == 'true':
            try:
                # Try to use pymt5linux for Wine bridge
                from pymt5linux import MetaTrader5
                logger.info("Using pymt5linux bridge for MT5 via Wine")

                class WineMT5Module:
                    """Wrapper for pymt5linux to match MT5 interface"""
                    def __init__(self):
                        self._mt5 = None

                    def initialize(self, **kwargs):
                        self._mt5 = MetaTrader5(host="localhost", port=18812)
                        return self._mt5.initialize(**kwargs)

                    def __getattr__(self, name):
                        if self._mt5:
                            return getattr(self._mt5, name)
                        raise AttributeError(f"MT5 not initialized. Call initialize() first.")

                return WineMT5Module()

            except ImportError:
                logger.warning("pymt5linux not available, using mock MT5")
        else:
            if not wine_available:
                logger.info("Wine not available, using mock MT5 module")
            else:
                logger.info("USE_WINE_MT5 not set, using mock MT5 module")

    # Default to mock MT5
    logger.info("Using mock MT5 module (default fallback)")
    from src.utils.mock_mt5 import (
        initialize, shutdown, last_error, symbol_info,
        symbol_info_tick, symbol_select, copy_ticks_from,
        copy_rates_from, account_info, positions_get, orders_get,
        COPY_TICKS_ALL, COPY_TICKS_INFO, COPY_TICKS_TRADE,
        TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_H1
    )

    class MockMT5Module:
        def __init__(self):
            self.initialize = initialize
            self.shutdown = shutdown
            self.last_error = last_error
            self.symbol_info = symbol_info
            self.symbol_info_tick = symbol_info_tick
            self.symbol_select = symbol_select
            self.copy_ticks_from = copy_ticks_from
            self.copy_rates_from = copy_rates_from
            self.account_info = account_info
            self.positions_get = positions_get
            self.orders_get = orders_get
            self.COPY_TICKS_ALL = COPY_TICKS_ALL
            self.COPY_TICKS_INFO = COPY_TICKS_INFO
            self.COPY_TICKS_TRADE = COPY_TICKS_TRADE
            self.TIMEFRAME_M1 = TIMEFRAME_M1
            self.TIMEFRAME_M5 = TIMEFRAME_M5
            self.TIMEFRAME_H1 = TIMEFRAME_H1

    return MockMT5Module()