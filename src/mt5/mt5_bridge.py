"""
MetaTrader 5 Bridge for WSL - Uses pymt5linux to connect to MT5 via Wine.
Provides a unified interface that works with both Wine-based MT5 and mock MT5.
"""

import os
import sys
import time
import subprocess
from typing import Optional, Dict, Any, Union
from datetime import datetime
from loguru import logger
import json

try:
    # Try to import pymt5linux for Wine bridge
    import pymt5linux
    PYMT5LINUX_AVAILABLE = True
    logger.info("pymt5linux imported successfully")
except ImportError:
    PYMT5LINUX_AVAILABLE = False
    logger.warning("pymt5linux not available - Wine bridge disabled")

from .mock_mt5 import MockMT5


class MT5Bridge:
    """
    Bridge class that provides unified access to MetaTrader 5.
    Automatically handles Wine setup, connection management, and fallback to mock.
    """

    def __init__(self, use_wine: bool = True, wine_prefix: str = None):
        self.use_wine = use_wine and PYMT5LINUX_AVAILABLE
        self.wine_prefix = wine_prefix or os.path.expanduser("~/.wine_mt5")
        self.mt5_path = None
        self.connected = False
        self.mock_mode = False

        # Initialize the appropriate backend
        if self.use_wine:
            self._init_wine_backend()
        else:
            self._init_mock_backend()

    def _init_wine_backend(self):
        """Initialize Wine-based MT5 backend"""
        try:
            # Set Wine prefix
            os.environ['WINEPREFIX'] = self.wine_prefix

            # Check if Wine is available
            result = subprocess.run(['wine', '--version'],
                                  capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("Wine not available")

            logger.info(f"Wine version: {result.stdout.strip()}")

            # Check for MT5 installation
            self.mt5_path = self._find_mt5_installation()
            if not self.mt5_path:
                logger.warning("MT5 not found in Wine - creating mock fallback")
                self._init_mock_backend()
                return

            logger.info(f"Found MT5 at: {self.mt5_path}")

        except Exception as e:
            logger.error(f"Wine backend initialization failed: {e}")
            self._init_mock_backend()

    def _init_mock_backend(self):
        """Initialize mock MT5 backend"""
        self.mock_mode = True
        self.mock_mt5 = MockMT5()
        logger.info("Using mock MT5 backend")

    def _find_mt5_installation(self) -> Optional[str]:
        """Find MT5 installation in Wine prefix"""
        possible_paths = [
            f"{self.wine_prefix}/drive_c/Program Files/MetaTrader 5/terminal64.exe",
            f"{self.wine_prefix}/drive_c/Program Files (x86)/MetaTrader 5/terminal64.exe",
            f"{self.wine_prefix}/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal/*/terminal64.exe"
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return None

    def initialize(self, path: str = "", login: int = 0, password: str = "",
                   server: str = "", timeout: int = 5000) -> bool:
        """Initialize MT5 connection"""
        if self.mock_mode:
            return self.mock_mt5.initialize(path, login, password, server, timeout)

        try:
            # Use pymt5linux for Wine connection
            result = pymt5linux.initialize(
                path=path or self.mt5_path,
                login=login,
                password=password,
                server=server,
                timeout=timeout
            )

            if result:
                self.connected = True
                logger.info("MT5 Wine connection established")
            else:
                logger.error("MT5 Wine connection failed")
                # Fallback to mock
                self._fallback_to_mock()
                return self.mock_mt5.initialize(path, login, password, server, timeout)

            return result

        except Exception as e:
            logger.error(f"MT5 Wine initialization error: {e}")
            # Fallback to mock
            self._fallback_to_mock()
            return self.mock_mt5.initialize(path, login, password, server, timeout)

    def _fallback_to_mock(self):
        """Fallback to mock mode when Wine fails"""
        if not self.mock_mode:
            logger.warning("Falling back to mock MT5 mode")
            self.mock_mode = True
            self.mock_mt5 = MockMT5()

    def shutdown(self):
        """Shutdown MT5 connection"""
        if self.mock_mode:
            self.mock_mt5.shutdown()
        else:
            try:
                pymt5linux.shutdown()
                self.connected = False
                logger.info("MT5 Wine connection closed")
            except Exception as e:
                logger.error(f"Error shutting down MT5: {e}")

    def symbol_info(self, symbol: str):
        """Get symbol information"""
        if self.mock_mode:
            return self.mock_mt5.symbol_info(symbol)

        try:
            return pymt5linux.symbol_info(symbol)
        except Exception as e:
            logger.error(f"Error getting symbol info: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.symbol_info(symbol)

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        """Select/deselect symbol"""
        if self.mock_mode:
            return self.mock_mt5.symbol_select(symbol, enable)

        try:
            return pymt5linux.symbol_select(symbol, enable)
        except Exception as e:
            logger.error(f"Error selecting symbol: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.symbol_select(symbol, enable)

    def symbol_info_tick(self, symbol: str):
        """Get current tick for symbol"""
        if self.mock_mode:
            return self.mock_mt5.symbol_info_tick(symbol)

        try:
            return pymt5linux.symbol_info_tick(symbol)
        except Exception as e:
            logger.error(f"Error getting tick: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.symbol_info_tick(symbol)

    def copy_ticks_from(self, symbol: str, date_from: datetime, count: int, flags: int):
        """Copy historical ticks"""
        if self.mock_mode:
            return self.mock_mt5.copy_ticks_from(symbol, date_from, count, flags)

        try:
            return pymt5linux.copy_ticks_from(symbol, date_from, count, flags)
        except Exception as e:
            logger.error(f"Error copying ticks: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.copy_ticks_from(symbol, date_from, count, flags)

    def account_info(self):
        """Get account information"""
        if self.mock_mode:
            return self.mock_mt5.account_info()

        try:
            return pymt5linux.account_info()
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.account_info()

    def last_error(self) -> tuple:
        """Get last error"""
        if self.mock_mode:
            return self.mock_mt5.last_error()

        try:
            return pymt5linux.last_error()
        except Exception as e:
            logger.error(f"Error getting last error: {e}")
            return (10000, str(e))

    def terminal_info(self):
        """Get terminal information"""
        if self.mock_mode:
            return self.mock_mt5.terminal_info()

        try:
            return pymt5linux.terminal_info()
        except Exception as e:
            logger.error(f"Error getting terminal info: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.terminal_info()

    def market_book_get(self, symbol: str):
        """Get market book/depth"""
        if self.mock_mode:
            return self.mock_mt5.market_book_get(symbol)

        try:
            return pymt5linux.market_book_get(symbol)
        except Exception as e:
            logger.error(f"Error getting market book: {e}")
            self._fallback_to_mock()
            return self.mock_mt5.market_book_get(symbol)

    def is_connected(self) -> bool:
        """Check if connected to MT5"""
        if self.mock_mode:
            return self.mock_mt5.connected
        return self.connected

    def get_mode(self) -> str:
        """Get current operating mode"""
        return "mock" if self.mock_mode else "wine"

    def test_connection(self) -> Dict[str, Any]:
        """Test the MT5 connection and return status"""
        status = {
            "mode": self.get_mode(),
            "connected": self.is_connected(),
            "wine_available": PYMT5LINUX_AVAILABLE,
            "wine_prefix": self.wine_prefix,
            "mt5_path": self.mt5_path,
            "errors": []
        }

        # Test basic operations
        try:
            # Test initialization
            if not self.is_connected():
                test_init = self.initialize(login=12345, server="test")
                status["init_test"] = test_init

            # Test symbol operations
            symbols = ["EURUSD", "GBPUSD"]
            for symbol in symbols:
                try:
                    info = self.symbol_info(symbol)
                    select_result = self.symbol_select(symbol, True)
                    tick = self.symbol_info_tick(symbol)

                    status[f"{symbol}_test"] = {
                        "info_available": info is not None,
                        "selection": select_result,
                        "tick_available": tick is not None
                    }
                except Exception as e:
                    status["errors"].append(f"{symbol}: {str(e)}")

            # Test account info
            try:
                account = self.account_info()
                status["account_test"] = account is not None
            except Exception as e:
                status["errors"].append(f"Account: {str(e)}")

        except Exception as e:
            status["errors"].append(f"General: {str(e)}")

        return status


class WineManager:
    """Manages Wine setup for MT5"""

    def __init__(self, wine_prefix: str = None):
        self.wine_prefix = wine_prefix or os.path.expanduser("~/.wine_mt5")

    def setup_wine_prefix(self) -> bool:
        """Set up Wine prefix for MT5"""
        try:
            logger.info(f"Setting up Wine prefix: {self.wine_prefix}")

            # Create Wine prefix
            env = os.environ.copy()
            env['WINEPREFIX'] = self.wine_prefix

            # Initialize Wine prefix
            result = subprocess.run([
                'winecfg', '/v', 'win10'
            ], env=env, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Wine prefix setup failed: {result.stderr}")
                return False

            # Install necessary components
            self._install_wine_components()

            logger.info("Wine prefix setup completed")
            return True

        except Exception as e:
            logger.error(f"Wine setup error: {e}")
            return False

    def _install_wine_components(self):
        """Install necessary Wine components for MT5"""
        try:
            env = os.environ.copy()
            env['WINEPREFIX'] = self.wine_prefix
            env['WINEDLLOVERRIDES'] = 'mscoree,msxml3=n'

            # Install vcrun2019 (Visual C++ Redistributable)
            logger.info("Installing Visual C++ Redistributable...")
            subprocess.run([
                'winetricks', '-q', 'vcrun2019'
            ], env=env, capture_output=True)

            # Install other dependencies
            dependencies = ['corefonts', 'ie8', 'wininet']
            for dep in dependencies:
                logger.info(f"Installing {dep}...")
                subprocess.run([
                    'winetricks', '-q', dep
                ], env=env, capture_output=True)

        except Exception as e:
            logger.warning(f"Component installation warning: {e}")

    def install_mt5(self, installer_path: str = None) -> bool:
        """Install MT5 in Wine"""
        try:
            if not installer_path:
                # Download MT5 installer
                installer_path = self._download_mt5_installer()

            if not os.path.exists(installer_path):
                logger.error(f"MT5 installer not found: {installer_path}")
                return False

            env = os.environ.copy()
            env['WINEPREFIX'] = self.wine_prefix

            # Run MT5 installer
            logger.info("Installing MT5 via Wine...")
            result = subprocess.run([
                'wine', installer_path, '/auto'
            ], env=env, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"MT5 installation failed: {result.stderr}")
                return False

            logger.info("MT5 installation completed")
            return True

        except Exception as e:
            logger.error(f"MT5 installation error: {e}")
            return False

    def _download_mt5_installer(self) -> str:
        """Download MT5 installer"""
        # This would download the official MT5 installer
        # For now, return a placeholder path
        installer_path = f"{self.wine_prefix}/mt5setup.exe"
        logger.warning(f"MT5 installer download not implemented. Expected at: {installer_path}")
        return installer_path

    def check_wine_health(self) -> Dict[str, Any]:
        """Check Wine installation health"""
        health = {
            "wine_available": False,
            "wine_version": None,
            "winetricks_available": False,
            "prefix_exists": False,
            "mt5_installed": False,
            "errors": []
        }

        try:
            # Check Wine
            result = subprocess.run(['wine', '--version'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                health["wine_available"] = True
                health["wine_version"] = result.stdout.strip()

            # Check Winetricks
            result = subprocess.run(['winetricks', '--version'],
                                  capture_output=True, text=True)
            health["winetricks_available"] = result.returncode == 0

            # Check prefix
            health["prefix_exists"] = os.path.exists(self.wine_prefix)

            # Check MT5
            mt5_bridge = MT5Bridge(use_wine=True, wine_prefix=self.wine_prefix)
            health["mt5_installed"] = mt5_bridge.mt5_path is not None

        except Exception as e:
            health["errors"].append(str(e))

        return health


# Global bridge instance
_bridge = None

def get_bridge(use_wine: bool = True, wine_prefix: str = None) -> MT5Bridge:
    """Get or create MT5 bridge instance"""
    global _bridge
    if _bridge is None:
        _bridge = MT5Bridge(use_wine=use_wine, wine_prefix=wine_prefix)
    return _bridge

# Convenience functions that match original MT5 API
def initialize(path: str = "", login: int = 0, password: str = "",
               server: str = "", timeout: int = 5000) -> bool:
    bridge = get_bridge()
    return bridge.initialize(path, login, password, server, timeout)

def shutdown():
    bridge = get_bridge()
    bridge.shutdown()

def symbol_info(symbol: str):
    bridge = get_bridge()
    return bridge.symbol_info(symbol)

def symbol_select(symbol: str, enable: bool = True) -> bool:
    bridge = get_bridge()
    return bridge.symbol_select(symbol, enable)

def symbol_info_tick(symbol: str):
    bridge = get_bridge()
    return bridge.symbol_info_tick(symbol)

def copy_ticks_from(symbol: str, date_from: datetime, count: int, flags: int):
    bridge = get_bridge()
    return bridge.copy_ticks_from(symbol, date_from, count, flags)

def account_info():
    bridge = get_bridge()
    return bridge.account_info()

def last_error() -> tuple:
    bridge = get_bridge()
    return bridge.last_error()

def terminal_info():
    bridge = get_bridge()
    return bridge.terminal_info()

def market_book_get(symbol: str):
    bridge = get_bridge()
    return bridge.market_book_get(symbol)

# Additional utilities
def test_mt5_connection() -> Dict[str, Any]:
    """Test MT5 connection and return detailed status"""
    bridge = get_bridge()
    return bridge.test_connection()

def check_wine_setup() -> Dict[str, Any]:
    """Check Wine setup for MT5"""
    wine_manager = WineManager()
    return wine_manager.check_wine_health()