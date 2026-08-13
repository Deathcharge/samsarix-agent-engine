# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A small, bounded agent layer for OpenAI-compatible model endpoints."""

from .engine import Agent, AgentOrchestrator, LLMAgentEngine
from .errors import (
    BudgetExceededError,
    ConfigurationError,
    GuardrailError,
    InputValidationError,
    ProviderError,
    SamsarixAgentError,
    StructuredOutputError,
    ToolApprovalError,
    ToolError,
    ToolExecutionError,
)
from .models import (
    AgentMetrics,
    ApprovalDecision,
    ApprovalHandler,
    ApprovalRequest,
    ChatMessage,
    Guardrail,
    GuardrailContext,
    GuardrailResult,
    JsonValue,
    ProviderResponse,
    ProviderStreamChunk,
    RunEvent,
    SessionSnapshot,
    ToolCall,
    ToolDefinition,
    ToolHandler,
    ToolMessage,
    ToolProviderResponse,
    parse_json_output,
)
from .providers import BaseLLMProvider, EchoProvider, OpenAICompatibleProvider

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "AgentMetrics",
    "AgentOrchestrator",
    "ApprovalDecision",
    "ApprovalHandler",
    "ApprovalRequest",
    "BaseLLMProvider",
    "BudgetExceededError",
    "ChatMessage",
    "ConfigurationError",
    "EchoProvider",
    "Guardrail",
    "GuardrailContext",
    "GuardrailError",
    "GuardrailResult",
    "InputValidationError",
    "JsonValue",
    "LLMAgentEngine",
    "OpenAICompatibleProvider",
    "ProviderError",
    "ProviderResponse",
    "ProviderStreamChunk",
    "RunEvent",
    "SamsarixAgentError",
    "SessionSnapshot",
    "StructuredOutputError",
    "ToolApprovalError",
    "ToolCall",
    "ToolDefinition",
    "ToolError",
    "ToolExecutionError",
    "ToolHandler",
    "ToolMessage",
    "ToolProviderResponse",
    "__version__",
    "parse_json_output",
]
