"""Test suite for agent functionality."""

import pytest


class TestAgentCreation:
    """Test agent creation."""
    
    @pytest.mark.agent
    def test_agent_creation(self, mock_agent):
        """Test agent creation."""
        assert mock_agent.agent_id == "agent-1"
        assert mock_agent.name == "TestAgent"
    
    @pytest.mark.agent
    def test_agent_personality(self, mock_agent):
        """Test agent personality."""
        assert mock_agent.personality == "helpful"


class TestAgentExecution:
    """Test agent execution."""
    
    @pytest.mark.agent
    def test_agent_execute(self, mock_agent):
        """Test agent execution."""
        result = mock_agent.execute()
        assert result["result"] == "success"
    
    @pytest.mark.agent
    def test_agent_state(self, mock_agent):
        """Test agent state."""
        state = mock_agent.get_state()
        assert state["status"] == "active"


class TestMultipleAgents:
    """Test multiple agents."""
    
    @pytest.mark.agent
    def test_agent_list(self, mock_agents_list):
        """Test agent list."""
        assert len(mock_agents_list) == 3
        assert mock_agents_list[0].agent_id == "agent-0"


class TestAgentConfiguration:
    """Test agent configuration."""
    
    @pytest.mark.agent
    def test_agent_config(self, mock_agent_config):
        """Test agent configuration."""
        assert mock_agent_config["agent_id"] == "agent-1"
        assert mock_agent_config["personality"] == "helpful"
        assert "reasoning" in mock_agent_config["capabilities"]
