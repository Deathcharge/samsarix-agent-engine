"""Comprehensive pytest configuration and fixtures for helix-hub-shared."""

import pytest
from unittest.mock import Mock, MagicMock, patch


# ============================================================================
# LLM Configuration Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_config():
    """Mock LLM configuration."""
    return {
        "model": "gpt-4",
        "provider": "openai",
        "temperature": 0.7,
        "max_tokens": 2000,
        "top_p": 0.9
    }


@pytest.fixture
def mock_agent_config():
    """Mock agent configuration."""
    return {
        "agent_id": "agent-1",
        "name": "TestAgent",
        "personality": "helpful",
        "capabilities": ["reasoning", "planning"],
        "llm_config": {"model": "gpt-4", "temperature": 0.7}
    }


# ============================================================================
# Agent Fixtures
# ============================================================================

@pytest.fixture
def mock_agent():
    """Mock agent instance."""
    agent = MagicMock()
    agent.agent_id = "agent-1"
    agent.name = "TestAgent"
    agent.personality = "helpful"
    agent.execute = MagicMock(return_value={"result": "success"})
    agent.get_state = MagicMock(return_value={"status": "active"})
    return agent


@pytest.fixture
def mock_agents_list():
    """Mock list of agents."""
    agents = []
    for i in range(3):
        agent = MagicMock()
        agent.agent_id = f"agent-{i}"
        agent.name = f"Agent{i}"
        agents.append(agent)
    return agents


# ============================================================================
# Engine Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_engine():
    """Mock LLM engine."""
    engine = MagicMock()
    engine.generate = MagicMock(return_value="Generated response")
    engine.stream_generate = MagicMock(return_value=["chunk1", "chunk2"])
    engine.get_config = MagicMock(return_value={"model": "gpt-4"})
    return engine


@pytest.fixture
def mock_agent_engine():
    """Mock agent engine."""
    engine = MagicMock()
    engine.register_agent = MagicMock(return_value=True)
    engine.execute_task = MagicMock(return_value={"result": "success"})
    engine.get_agent = MagicMock(return_value=MagicMock())
    engine.list_agents = MagicMock(return_value=[])
    return engine


# ============================================================================
# Communication Fixtures
# ============================================================================

@pytest.fixture
def mock_message():
    """Mock message."""
    return {
        "id": "msg-1",
        "sender": "agent-1",
        "recipient": "agent-2",
        "content": "Hello",
        "timestamp": 1234567890
    }


@pytest.fixture
def mock_communication_logger():
    """Mock communication logger."""
    logger = MagicMock()
    logger.log_message = MagicMock(return_value=True)
    logger.get_history = MagicMock(return_value=[])
    logger.clear_history = MagicMock(return_value=True)
    return logger


# ============================================================================
# Coordination Fixtures
# ============================================================================

@pytest.fixture
def mock_coordination_context():
    """Mock coordination context."""
    return {
        "agents": ["agent-1", "agent-2", "agent-3"],
        "task": "collaborative_task",
        "status": "active",
        "created_at": 1234567890
    }


@pytest.fixture
def mock_coordinator():
    """Mock coordinator."""
    coordinator = MagicMock()
    coordinator.coordinate = MagicMock(return_value={"status": "coordinated"})
    coordinator.get_status = MagicMock(return_value="active")
    coordinator.shutdown = MagicMock(return_value=True)
    return coordinator


# ============================================================================
# Performance Fixtures
# ============================================================================

@pytest.fixture
def mock_performance_metrics():
    """Mock performance metrics."""
    return {
        "response_time": 0.5,
        "throughput": 100,
        "error_rate": 0.01,
        "cpu_usage": 45.2,
        "memory_usage": 512
    }


@pytest.fixture
def mock_performance_service():
    """Mock performance service."""
    service = MagicMock()
    service.get_metrics = MagicMock(return_value={})
    service.record_metric = MagicMock(return_value=True)
    service.get_agent_performance = MagicMock(return_value={})
    return service


# ============================================================================
# Scenario Fixtures
# ============================================================================

@pytest.fixture
def multi_agent_scenario():
    """Multi-agent collaboration scenario."""
    return {
        "agents": ["agent-1", "agent-2", "agent-3"],
        "task": "collaborative_analysis",
        "expected_result": "comprehensive_analysis",
        "timeout": 30
    }


@pytest.fixture
def error_scenario():
    """Error handling scenario."""
    return {
        "error_type": "agent_unavailable",
        "retry_count": 3,
        "fallback_strategy": "use_alternative_agent",
        "should_recover": True
    }


@pytest.fixture
def performance_scenario():
    """Performance testing scenario."""
    return {
        "num_agents": 10,
        "num_tasks": 100,
        "concurrent_tasks": 5,
        "expected_throughput": 50
    }
