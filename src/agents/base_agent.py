"""
Base Agent Architecture for the HFT System.
Implements the fundamental agent pattern that all specialized agents inherit from.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import threading
from queue import Queue, Empty
import uuid
from loguru import logger
import traceback


class AgentState(Enum):
    """Agent lifecycle states"""
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MessageType(Enum):
    """Inter-agent message types"""
    DATA = "data"
    COMMAND = "command"
    STATUS = "status"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    RESULT = "result"


@dataclass
class Message:
    """Inter-agent message structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    receiver: str = ""
    type: MessageType = MessageType.DATA
    payload: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None
    priority: int = 0  # Higher priority = more important


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the HFT system.
    Provides common functionality for lifecycle management, messaging, and error handling.
    """

    def __init__(self, name: str, agent_type: str):
        """Initialize base agent"""
        self.name = name
        self.agent_type = agent_type
        self.id = f"{agent_type}_{uuid.uuid4().hex[:8]}"
        self.state = AgentState.INITIALIZED

        # Message queues
        self.inbox = Queue()
        self.outbox = Queue()

        # Event loop for async operations
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Callbacks and handlers
        self._message_handlers: Dict[MessageType, List[Callable]] = {
            msg_type: [] for msg_type in MessageType
        }

        # Performance metrics
        self.metrics = {
            "messages_processed": 0,
            "messages_sent": 0,
            "errors": 0,
            "start_time": None,
            "total_processing_time": 0,
        }

        # Error handling
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds

        logger.info(f"Agent {self.name} ({self.id}) initialized")

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize agent resources and connections"""
        pass

    @abstractmethod
    async def process(self, message: Message) -> Optional[Message]:
        """Process incoming message and return optional response"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup agent resources before shutdown"""
        pass

    def start(self) -> None:
        """Start the agent in a separate thread"""
        if self.state != AgentState.INITIALIZED:
            logger.warning(f"Agent {self.name} already started or in invalid state")
            return

        self.state = AgentState.STARTING
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        logger.info(f"Agent {self.name} started")

    def stop(self) -> None:
        """Stop the agent gracefully"""
        if self.state not in [AgentState.RUNNING, AgentState.PAUSED]:
            logger.warning(f"Agent {self.name} not running")
            return

        self.state = AgentState.STOPPING
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)

    def pause(self) -> None:
        """Pause agent processing"""
        if self.state == AgentState.RUNNING:
            self.state = AgentState.PAUSED
            logger.info(f"Agent {self.name} paused")

    def resume(self) -> None:
        """Resume agent processing"""
        if self.state == AgentState.PAUSED:
            self.state = AgentState.RUNNING
            logger.info(f"Agent {self.name} resumed")

    def send_message(self, message: Message) -> None:
        """Send message to another agent"""
        message.sender = self.id
        self.outbox.put(message)
        self.metrics["messages_sent"] += 1

    def receive_message(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Receive message from inbox"""
        try:
            message = self.inbox.get(timeout=timeout)
            self.metrics["messages_processed"] += 1
            return message
        except Empty:
            return None

    def register_handler(self, message_type: MessageType, handler: Callable) -> None:
        """Register a handler for specific message types"""
        self._message_handlers[message_type].append(handler)

    async def handle_message(self, message: Message) -> Optional[Message]:
        """Handle incoming message with registered handlers or default processing"""
        try:
            # Call registered handlers
            handlers = self._message_handlers.get(message.type, [])
            for handler in handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)

            # Call abstract process method
            return await self.process(message)

        except Exception as e:
            self.metrics["errors"] += 1
            logger.error(f"Error handling message in {self.name}: {e}\n{traceback.format_exc()}")
            return self._create_error_message(message, str(e))

    def _create_error_message(self, original: Message, error: str) -> Message:
        """Create error response message"""
        return Message(
            sender=self.id,
            receiver=original.sender,
            type=MessageType.ERROR,
            payload={"error": error, "original_message": original.id},
            correlation_id=original.id,
        )

    def _run_event_loop(self) -> None:
        """Run the agent's event loop in a separate thread"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._agent_lifecycle())
        except Exception as e:
            logger.error(f"Fatal error in agent {self.name}: {e}\n{traceback.format_exc()}")
            self.state = AgentState.ERROR
        finally:
            self._loop.close()

    async def _agent_lifecycle(self) -> None:
        """Main agent lifecycle"""
        try:
            # Initialize
            await self.initialize()
            self.state = AgentState.RUNNING
            self.metrics["start_time"] = datetime.now()

            # Main processing loop
            while self.state in [AgentState.RUNNING, AgentState.PAUSED]:
                if self.state == AgentState.PAUSED:
                    await asyncio.sleep(0.1)
                    continue

                # Process messages
                message = self.receive_message(timeout=0.01)
                if message:
                    start_time = datetime.now()
                    response = await self.handle_message(message)
                    processing_time = (datetime.now() - start_time).total_seconds()
                    self.metrics["total_processing_time"] += processing_time

                    if response:
                        self.send_message(response)

                # Allow other tasks to run
                await asyncio.sleep(0.001)

        except Exception as e:
            logger.error(f"Error in agent lifecycle {self.name}: {e}")
            self.state = AgentState.ERROR
            raise

    async def _shutdown(self) -> None:
        """Shutdown agent gracefully"""
        try:
            logger.info(f"Shutting down agent {self.name}")
            await self.cleanup()
            self.state = AgentState.STOPPED
            logger.info(f"Agent {self.name} stopped successfully")
        except Exception as e:
            logger.error(f"Error during agent shutdown {self.name}: {e}")
            self.state = AgentState.ERROR

    def get_status(self) -> Dict[str, Any]:
        """Get agent status and metrics"""
        uptime = None
        if self.metrics["start_time"]:
            uptime = (datetime.now() - self.metrics["start_time"]).total_seconds()

        return {
            "id": self.id,
            "name": self.name,
            "type": self.agent_type,
            "state": self.state.value,
            "metrics": {
                **self.metrics,
                "uptime_seconds": uptime,
                "avg_processing_time": (
                    self.metrics["total_processing_time"] / max(1, self.metrics["messages_processed"])
                ),
            },
            "inbox_size": self.inbox.qsize(),
            "outbox_size": self.outbox.qsize(),
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, id={self.id}, state={self.state.value})"