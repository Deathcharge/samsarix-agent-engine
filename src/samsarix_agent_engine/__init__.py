# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A small, bounded agent layer for OpenAI-compatible model endpoints."""

from .engine import Agent, AgentOrchestrator, LLMAgentEngine
from .errors import (
    BudgetExceededError,
    ConfigurationError,
    InputValidationError,
    ProviderError,
    SamsarixAgentError,
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
    "InputValidationError",
    "LLMAgentEngine",
    "OpenAICompatibleProvider",
    "ProviderError",
    "ProviderResponse",
    "SamsarixAgentError",
    "__version__",
]
