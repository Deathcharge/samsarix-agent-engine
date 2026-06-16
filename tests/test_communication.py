"""Test suite for communication functionality."""

import pytest


class TestMessaging:
    """Test messaging."""
    
    @pytest.mark.communication
    def test_message_creation(self, mock_message):
        """Test message creation."""
        assert mock_message["sender"] == "agent-1"
        assert mock_message["recipient"] == "agent-2"
        assert mock_message["content"] == "Hello"
    
    @pytest.mark.communication
    def test_message_id(self, mock_message):
        """Test message ID."""
        assert mock_message["id"] == "msg-1"


class TestCommunicationLogger:
    """Test communication logger."""
    
    @pytest.mark.communication
    def test_logger_creation(self, mock_communication_logger):
        """Test logger creation."""
        assert mock_communication_logger is not None
    
    @pytest.mark.communication
    def test_log_message(self, mock_communication_logger):
        """Test logging message."""
        result = mock_communication_logger.log_message()
        assert result is True
    
    @pytest.mark.communication
    def test_get_history(self, mock_communication_logger):
        """Test getting history."""
        history = mock_communication_logger.get_history()
        assert isinstance(history, list)
    
    @pytest.mark.communication
    def test_clear_history(self, mock_communication_logger):
        """Test clearing history."""
        result = mock_communication_logger.clear_history()
        assert result is True
