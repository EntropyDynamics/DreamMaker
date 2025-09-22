"""
Coordinator Agent - The orchestrator of the HFT system.
Manages all other agents and ensures proper communication flow.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import asyncio
import uuid
from datetime import datetime
from loguru import logger

from .base_agent import BaseAgent, Message, MessageType, AgentState


@dataclass
class AgentRegistry:
    """Registry entry for managed agents"""
    agent: BaseAgent
    role: str
    capabilities: List[str]
    priority: int = 0
    last_heartbeat: Optional[datetime] = None


class CoordinatorAgent(BaseAgent):
    """
    Central coordinator that manages all specialized agents in the system.
    Implements the hierarchical swarm topology with queen-worker pattern.
    """

    def __init__(self):
        super().__init__("Coordinator", "coordinator")
        self.agents: Dict[str, AgentRegistry] = {}
        self.routing_table: Dict[str, List[str]] = {}
        self.heartbeat_interval = 5.0  # seconds
        self.consensus_threshold = 0.6  # 60% agreement needed

    async def initialize(self) -> None:
        """Initialize the coordinator"""
        logger.info("Initializing Coordinator Agent")
        # Start heartbeat monitoring
        asyncio.create_task(self._heartbeat_monitor())

    async def process(self, message: Message) -> Optional[Message]:
        """Process coordinator-specific messages"""
        if message.type == MessageType.COMMAND:
            return await self._handle_command(message)
        elif message.type == MessageType.STATUS:
            return await self._handle_status(message)
        elif message.type == MessageType.DATA:
            return await self._route_message(message)
        return None

    async def cleanup(self) -> None:
        """Cleanup coordinator resources"""
        logger.info("Cleaning up Coordinator Agent")
        # Stop all managed agents
        for agent_id, registry in self.agents.items():
            if registry.agent.state == AgentState.RUNNING:
                registry.agent.stop()

    def register_agent(
        self,
        agent: BaseAgent,
        role: str,
        capabilities: List[str],
        priority: int = 0
    ) -> bool:
        """Register a new agent with the coordinator"""
        try:
            if agent.id in self.agents:
                logger.warning(f"Agent {agent.id} already registered")
                return False

            registry = AgentRegistry(
                agent=agent,
                role=role,
                capabilities=capabilities,
                priority=priority,
                last_heartbeat=datetime.now()
            )
            self.agents[agent.id] = registry

            # Update routing table
            for capability in capabilities:
                if capability not in self.routing_table:
                    self.routing_table[capability] = []
                self.routing_table[capability].append(agent.id)

            logger.info(f"Registered agent {agent.name} ({agent.id}) with role {role}")
            return True

        except Exception as e:
            logger.error(f"Failed to register agent: {e}")
            return False

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the coordinator"""
        try:
            if agent_id not in self.agents:
                logger.warning(f"Agent {agent_id} not found")
                return False

            registry = self.agents[agent_id]

            # Remove from routing table
            for capability in registry.capabilities:
                if capability in self.routing_table:
                    self.routing_table[capability].remove(agent_id)
                    if not self.routing_table[capability]:
                        del self.routing_table[capability]

            # Remove from registry
            del self.agents[agent_id]
            logger.info(f"Unregistered agent {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister agent: {e}")
            return False

    async def broadcast_message(self, message: Message, role: Optional[str] = None) -> None:
        """Broadcast message to all agents or agents with specific role"""
        recipients = []
        if role:
            recipients = [
                agent_id for agent_id, registry in self.agents.items()
                if registry.role == role
            ]
        else:
            recipients = list(self.agents.keys())

        for agent_id in recipients:
            if agent_id in self.agents:
                agent_message = Message(
                    sender=self.id,
                    receiver=agent_id,
                    type=message.type,
                    payload=message.payload,
                    correlation_id=message.id
                )
                self.agents[agent_id].agent.inbox.put(agent_message)

    async def request_consensus(
        self,
        question: Dict[str, Any],
        agents: List[str],
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Request consensus from multiple agents on a decision"""
        correlation_id = str(uuid.uuid4())
        responses = {}

        # Send request to all specified agents
        for agent_id in agents:
            if agent_id in self.agents:
                request = Message(
                    sender=self.id,
                    receiver=agent_id,
                    type=MessageType.COMMAND,
                    payload={"action": "vote", "question": question},
                    correlation_id=correlation_id
                )
                self.agents[agent_id].agent.inbox.put(request)

        # Collect responses
        start_time = datetime.now()
        while len(responses) < len(agents):
            if (datetime.now() - start_time).total_seconds() > timeout:
                break

            # Check for responses
            for agent_id in agents:
                if agent_id not in responses and agent_id in self.agents:
                    try:
                        # Non-blocking check for response
                        message = self.agents[agent_id].agent.outbox.get_nowait()
                        if message.correlation_id == correlation_id:
                            responses[agent_id] = message.payload
                    except:
                        pass

            await asyncio.sleep(0.1)

        # Calculate consensus
        if responses:
            votes = list(responses.values())
            positive_votes = sum(1 for v in votes if v.get("vote", False))
            consensus_reached = (positive_votes / len(votes)) >= self.consensus_threshold

            return {
                "consensus": consensus_reached,
                "positive_ratio": positive_votes / len(votes),
                "responses": responses,
                "total_agents": len(agents),
                "responded": len(responses)
            }

        return {
            "consensus": False,
            "positive_ratio": 0,
            "responses": {},
            "total_agents": len(agents),
            "responded": 0
        }

    async def _route_message(self, message: Message) -> Optional[Message]:
        """Route message to appropriate agent based on capabilities"""
        if "capability" not in message.payload:
            logger.warning("Message missing capability field for routing")
            return None

        capability = message.payload["capability"]
        if capability not in self.routing_table:
            logger.warning(f"No agents registered for capability: {capability}")
            return None

        # Select agent based on priority and availability
        available_agents = [
            agent_id for agent_id in self.routing_table[capability]
            if self.agents[agent_id].agent.state == AgentState.RUNNING
        ]

        if not available_agents:
            logger.warning(f"No available agents for capability: {capability}")
            return None

        # Route to highest priority available agent
        selected_agent = max(
            available_agents,
            key=lambda x: self.agents[x].priority
        )

        # Forward message
        routed_message = Message(
            sender=self.id,
            receiver=selected_agent,
            type=message.type,
            payload=message.payload,
            correlation_id=message.correlation_id or message.id
        )
        self.agents[selected_agent].agent.inbox.put(routed_message)
        logger.debug(f"Routed message to agent {selected_agent}")

        return None

    async def _handle_command(self, message: Message) -> Optional[Message]:
        """Handle command messages"""
        command = message.payload.get("command")

        if command == "start_all":
            for agent_id, registry in self.agents.items():
                if registry.agent.state == AgentState.INITIALIZED:
                    registry.agent.start()
            return Message(
                sender=self.id,
                receiver=message.sender,
                type=MessageType.RESULT,
                payload={"status": "All agents started"},
                correlation_id=message.id
            )

        elif command == "stop_all":
            for agent_id, registry in self.agents.items():
                if registry.agent.state == AgentState.RUNNING:
                    registry.agent.stop()
            return Message(
                sender=self.id,
                receiver=message.sender,
                type=MessageType.RESULT,
                payload={"status": "All agents stopped"},
                correlation_id=message.id
            )

        elif command == "get_status":
            status = {
                "coordinator": self.get_status(),
                "agents": {
                    agent_id: registry.agent.get_status()
                    for agent_id, registry in self.agents.items()
                },
                "routing_table": self.routing_table
            }
            return Message(
                sender=self.id,
                receiver=message.sender,
                type=MessageType.RESULT,
                payload=status,
                correlation_id=message.id
            )

        return None

    async def _handle_status(self, message: Message) -> None:
        """Handle status updates from agents"""
        if message.sender in self.agents:
            self.agents[message.sender].last_heartbeat = datetime.now()

    async def _heartbeat_monitor(self) -> None:
        """Monitor agent heartbeats and detect failures"""
        while self.state == AgentState.RUNNING:
            current_time = datetime.now()

            for agent_id, registry in self.agents.items():
                if registry.last_heartbeat:
                    time_since_heartbeat = (
                        current_time - registry.last_heartbeat
                    ).total_seconds()

                    if time_since_heartbeat > self.heartbeat_interval * 3:
                        logger.warning(f"Agent {agent_id} missed heartbeat")
                        # Could implement recovery or restart logic here

            # Send heartbeat request
            heartbeat = Message(
                sender=self.id,
                type=MessageType.HEARTBEAT,
                payload={"timestamp": current_time}
            )
            await self.broadcast_message(heartbeat)

            await asyncio.sleep(self.heartbeat_interval)

    def get_network_topology(self) -> Dict[str, Any]:
        """Get the current network topology of agents"""
        return {
            "topology_type": "hierarchical",
            "coordinator": {
                "id": self.id,
                "name": self.name,
                "state": self.state.value
            },
            "workers": [
                {
                    "id": agent_id,
                    "name": registry.agent.name,
                    "role": registry.role,
                    "state": registry.agent.state.value,
                    "capabilities": registry.capabilities,
                    "priority": registry.priority
                }
                for agent_id, registry in self.agents.items()
            ],
            "connections": self.routing_table,
            "total_agents": len(self.agents) + 1  # +1 for coordinator
        }