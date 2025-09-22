"""
Data Connection Agent - Interface with MetaTrader 5 for real-time data.
Handles tick data reception, LOB reconstruction, and data streaming.
"""

from typing import Dict, List, Optional, Any, Deque
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import numpy as np
import pandas as pd
from loguru import logger

# Use the MT5 bridge to handle both mock and real MT5
from src.utils.mt5_bridge import get_mt5_module
mt5 = get_mt5_module()

from .base_agent import BaseAgent, Message, MessageType
from config.config import MT5Config, DataConfig


@dataclass
class Tick:
    """Market tick data structure"""
    time: datetime
    bid: float
    ask: float
    last: float
    volume: float
    flags: int
    time_msc: int

    @classmethod
    def from_mt5(cls, mt5_tick) -> "Tick":
        """Create Tick from MT5 tick data"""
        return cls(
            time=datetime.fromtimestamp(mt5_tick.time),
            bid=mt5_tick.bid,
            ask=mt5_tick.ask,
            last=mt5_tick.last,
            volume=mt5_tick.volume_real,
            flags=mt5_tick.flags,
            time_msc=mt5_tick.time_msc
        )


@dataclass
class OrderBookLevel:
    """Single level in the order book"""
    price: float
    volume: float
    orders: int = 1


@dataclass
class OrderBook:
    """Limit Order Book (LOB) structure"""
    symbol: str
    timestamp: datetime
    bid_levels: List[OrderBookLevel] = field(default_factory=list)
    ask_levels: List[OrderBookLevel] = field(default_factory=list)

    @property
    def best_bid(self) -> Optional[float]:
        return self.bid_levels[0].price if self.bid_levels else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.ask_levels[0].price if self.ask_levels else None

    @property
    def spread(self) -> float:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return 0.0

    @property
    def micro_price(self) -> float:
        """Volume-weighted mid price"""
        if self.bid_levels and self.ask_levels:
            bid_vol = self.bid_levels[0].volume
            ask_vol = self.ask_levels[0].volume
            total_vol = bid_vol + ask_vol
            if total_vol > 0:
                return (self.best_bid * ask_vol + self.best_ask * bid_vol) / total_vol
        return self.mid_price


class DataAgent(BaseAgent):
    """
    Agent responsible for data connection and streaming from MetaTrader 5.
    Maintains connection, receives ticks, reconstructs LOB, and streams to other agents.
    """

    def __init__(self, mt5_config: MT5Config, data_config: DataConfig):
        super().__init__("DataAgent", "data_connector")
        self.mt5_config = mt5_config
        self.data_config = data_config

        # MT5 connection state
        self.connected = False
        self.symbol_info = None

        # Data buffers
        self.tick_buffer: Deque[Tick] = deque(maxlen=data_config.buffer_size)
        self.book_buffer: Deque[OrderBook] = deque(maxlen=data_config.buffer_size)

        # Bar construction
        self.tick_bars: List[pd.DataFrame] = []
        self.volume_bars: List[pd.DataFrame] = []
        self.dollar_bars: List[pd.DataFrame] = []
        self.current_bar_ticks = []
        self.current_bar_volume = 0
        self.current_bar_dollar = 0

        # Statistics
        self.stats = {
            "ticks_received": 0,
            "books_constructed": 0,
            "bars_created": 0,
            "connection_attempts": 0,
            "disconnections": 0,
        }

    async def initialize(self) -> None:
        """Initialize MT5 connection"""
        logger.info("Initializing Data Agent")
        await self._connect_mt5()

        # Start data streaming tasks
        if self.connected:
            asyncio.create_task(self._stream_ticks())
            asyncio.create_task(self._construct_bars())

    async def process(self, message: Message) -> Optional[Message]:
        """Process data-related messages"""
        command = message.payload.get("command")

        if command == "get_latest_tick":
            if self.tick_buffer:
                return Message(
                    sender=self.id,
                    receiver=message.sender,
                    type=MessageType.DATA,
                    payload={"tick": self.tick_buffer[-1]},
                    correlation_id=message.id
                )

        elif command == "get_latest_book":
            if self.book_buffer:
                return Message(
                    sender=self.id,
                    receiver=message.sender,
                    type=MessageType.DATA,
                    payload={"book": self.book_buffer[-1]},
                    correlation_id=message.id
                )

        elif command == "get_historical_data":
            period = message.payload.get("period", 1000)
            data = await self._fetch_historical_data(period)
            return Message(
                sender=self.id,
                receiver=message.sender,
                type=MessageType.DATA,
                payload={"historical_data": data},
                correlation_id=message.id
            )

        elif command == "reconnect":
            await self._reconnect()
            return Message(
                sender=self.id,
                receiver=message.sender,
                type=MessageType.STATUS,
                payload={"connected": self.connected},
                correlation_id=message.id
            )

        return None

    async def cleanup(self) -> None:
        """Cleanup MT5 connection"""
        logger.info("Cleaning up Data Agent")
        if self.connected:
            mt5.shutdown()
            self.connected = False

    async def _connect_mt5(self) -> bool:
        """Establish connection to MetaTrader 5"""
        try:
            self.stats["connection_attempts"] += 1

            # Initialize MT5
            if not mt5.initialize(
                path=self.mt5_config.path,
                login=self.mt5_config.account,
                password=self.mt5_config.password,
                server=self.mt5_config.server,
                timeout=self.mt5_config.timeout
            ):
                error = mt5.last_error()
                logger.error(f"MT5 initialization failed: {error}")
                return False

            # Get symbol info
            self.symbol_info = mt5.symbol_info(self.mt5_config.symbol)
            if self.symbol_info is None:
                logger.error(f"Symbol {self.mt5_config.symbol} not found")
                mt5.shutdown()
                return False

            # Select symbol
            if not mt5.symbol_select(self.mt5_config.symbol, True):
                logger.error(f"Failed to select symbol {self.mt5_config.symbol}")
                mt5.shutdown()
                return False

            self.connected = True
            logger.info(f"Connected to MT5: {self.mt5_config.server}")
            logger.info(f"Symbol: {self.mt5_config.symbol}")
            logger.info(f"Account: {self.mt5_config.account}")

            return True

        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False

    async def _reconnect(self) -> None:
        """Reconnect to MT5 after disconnection"""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            self.stats["disconnections"] += 1

        await asyncio.sleep(1)
        await self._connect_mt5()

    async def _stream_ticks(self) -> None:
        """Stream real-time tick data from MT5"""
        logger.info("Starting tick streaming")

        while self.connected and self.state.value == "running":
            try:
                # Get latest ticks
                ticks = mt5.symbol_info_tick(self.mt5_config.symbol)
                if ticks is None:
                    await asyncio.sleep(0.01)
                    continue

                # Convert to internal format
                tick = Tick.from_mt5(ticks)
                self.tick_buffer.append(tick)
                self.stats["ticks_received"] += 1

                # Reconstruct order book (simplified for now)
                book = self._reconstruct_book(tick)
                self.book_buffer.append(book)
                self.stats["books_constructed"] += 1

                # Send to feature agents
                await self._broadcast_tick(tick)
                await self._broadcast_book(book)

                # Add to current bar
                self.current_bar_ticks.append(tick)
                self.current_bar_volume += tick.volume
                self.current_bar_dollar += tick.last * tick.volume

            except Exception as e:
                logger.error(f"Error streaming ticks: {e}")
                await self._reconnect()

            await asyncio.sleep(0.001)  # Small delay to prevent CPU overload

    def _reconstruct_book(self, tick: Tick) -> OrderBook:
        """
        Reconstruct order book from tick data.
        This is a simplified version - real implementation would use market depth data.
        """
        # For now, create a simple book with best bid/ask
        book = OrderBook(
            symbol=self.mt5_config.symbol,
            timestamp=tick.time
        )

        # Add best levels (simplified)
        if tick.bid > 0:
            book.bid_levels.append(OrderBookLevel(price=tick.bid, volume=100))

        if tick.ask > 0:
            book.ask_levels.append(OrderBookLevel(price=tick.ask, volume=100))

        # In production, we would get full market depth here
        # depth = mt5.market_book_get(self.mt5_config.symbol)
        # and reconstruct full LOB

        return book

    async def _construct_bars(self) -> None:
        """Construct information bars (tick, volume, dollar)"""
        while self.state.value == "running":
            try:
                # Tick bars
                if len(self.current_bar_ticks) >= self.data_config.tick_bar_size:
                    tick_bar = self._create_bar(self.current_bar_ticks)
                    self.tick_bars.append(tick_bar)
                    self.current_bar_ticks = []
                    self.stats["bars_created"] += 1
                    await self._broadcast_bar(tick_bar, "tick")

                # Volume bars
                if self.current_bar_volume >= self.data_config.volume_bar_size:
                    volume_bar = self._create_bar(self.current_bar_ticks)
                    self.volume_bars.append(volume_bar)
                    self.current_bar_volume = 0
                    await self._broadcast_bar(volume_bar, "volume")

                # Dollar bars
                if self.current_bar_dollar >= self.data_config.dollar_bar_size:
                    dollar_bar = self._create_bar(self.current_bar_ticks)
                    self.dollar_bars.append(dollar_bar)
                    self.current_bar_dollar = 0
                    await self._broadcast_bar(dollar_bar, "dollar")

            except Exception as e:
                logger.error(f"Error constructing bars: {e}")

            await asyncio.sleep(0.1)

    def _create_bar(self, ticks: List[Tick]) -> pd.DataFrame:
        """Create OHLCV bar from ticks"""
        if not ticks:
            return pd.DataFrame()

        prices = [t.last for t in ticks]
        volumes = [t.volume for t in ticks]

        bar = pd.DataFrame({
            "timestamp": [ticks[-1].time],
            "open": [prices[0]],
            "high": [max(prices)],
            "low": [min(prices)],
            "close": [prices[-1]],
            "volume": [sum(volumes)],
            "tick_count": [len(ticks)],
            "buy_volume": [sum(v for t, v in zip(ticks, volumes) if t.last >= t.ask)],
            "sell_volume": [sum(v for t, v in zip(ticks, volumes) if t.last <= t.bid)],
        })

        return bar

    async def _broadcast_tick(self, tick: Tick) -> None:
        """Broadcast tick to interested agents"""
        message = Message(
            sender=self.id,
            type=MessageType.DATA,
            payload={
                "data_type": "tick",
                "tick": tick,
                "timestamp": tick.time
            }
        )
        self.send_message(message)

    async def _broadcast_book(self, book: OrderBook) -> None:
        """Broadcast order book to interested agents"""
        message = Message(
            sender=self.id,
            type=MessageType.DATA,
            payload={
                "data_type": "book",
                "book": book,
                "timestamp": book.timestamp
            }
        )
        self.send_message(message)

    async def _broadcast_bar(self, bar: pd.DataFrame, bar_type: str) -> None:
        """Broadcast constructed bar to interested agents"""
        message = Message(
            sender=self.id,
            type=MessageType.DATA,
            payload={
                "data_type": "bar",
                "bar_type": bar_type,
                "bar": bar.to_dict(),
                "timestamp": datetime.now()
            }
        )
        self.send_message(message)

    async def _fetch_historical_data(self, periods: int) -> pd.DataFrame:
        """Fetch historical data from MT5"""
        try:
            # Get historical ticks
            ticks = mt5.copy_ticks_from(
                self.mt5_config.symbol,
                datetime.now(),
                periods,
                mt5.COPY_TICKS_ALL
            )

            if ticks is None or len(ticks) == 0:
                logger.warning("No historical ticks available")
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(ticks)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)

            return df

        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return pd.DataFrame()

    def get_statistics(self) -> Dict[str, Any]:
        """Get agent statistics"""
        base_stats = self.get_status()
        base_stats.update({
            "data_stats": self.stats,
            "buffer_sizes": {
                "ticks": len(self.tick_buffer),
                "books": len(self.book_buffer),
                "tick_bars": len(self.tick_bars),
                "volume_bars": len(self.volume_bars),
                "dollar_bars": len(self.dollar_bars),
            },
            "connection": {
                "connected": self.connected,
                "symbol": self.mt5_config.symbol,
                "server": self.mt5_config.server,
            }
        })
        return base_stats