"""A small, bounded agent layer for OpenAI-compatible model endpoints."""

from .engine import Agent, AgentOrchestrator, LLMAgentEngine
from .errors import (
    BudgetExceededError,
    ConfigurationError,
    HelixAgentError,
    InputValidationError,
    ProviderError,
)
from .models import AgentMetrics, ChatMessage, ProviderResponse
from .providers import BaseLLMProvider, EchoProvider, OpenAICompatibleProvider

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "AgentMetrics",
    "AgentOrchestrator",
    "BaseLLMProvider",
    "BudgetExceededError",
    "ChatMessage",
    "ConfigurationError",
    "EchoProvider",
    "HelixAgentError",
    "InputValidationError",
    "LLMAgentEngine",
    "OpenAICompatibleProvider",
    "ProviderError",
    "ProviderResponse",
    "__version__",
]
