# Competitive position

Assessment date: 2026-08-08. This is a product-boundary comparison, not a claim
that the projects have identical scope or maturity.

## The wedge

Samsarix Agent Engine is a dependency-light, telemetry-free runtime for bounded
OpenAI-compatible calls inside an application the developer already operates. Its
useful differentiation is the combination of:

- one required runtime dependency (`httpx`);
- no hosted control plane, implicit telemetry, database, or vendor SDK;
- strict local budgets for requests, retries, response bytes/characters, sessions,
  history, streaming, tool rounds/calls/arguments/results, and orchestration fanout;
- strict structured-output parsing without a validation-framework dependency;
- local input/output guardrails and content-free lifecycle events;
- portable versioned session snapshots with caller-owned storage and encryption;
- function tools that require approval by default and refuse execution when the
  remaining model-request budget cannot consume the result.

The package should compete on auditability and small operational surface, not on
the number of integrations or orchestration primitives.

## Current alternatives

| Project | Officially documented strengths | When it is a better fit | Samsarix distinction |
| --- | --- | --- | --- |
| OpenAI Agents SDK | Agents, agent-as-tools, handoffs, guardrails, sessions, human-in-the-loop, tracing, and an automatic agent loop. | Deep OpenAI platform integration, handoffs, hosted tracing, and a higher-level loop. | One compatible HTTP protocol, no SDK/trace backend, local content-free events, explicit hard budgets. |
| LangGraph | Thread/checkpoint persistence, interrupts for human review, durable execution, and multiple streaming modes. | Long-running stateful graphs, resumability, branching, and durable human review. | No graph/checkpointer abstraction; smaller synchronous-integration surface and explicit portable snapshots. |
| Pydantic AI | Typed dependency injection/output, many model providers, tools, human approval, durable execution integrations, OpenTelemetry, and evals. | Strong typed-model ecosystem, provider breadth, observability, and evaluation workflows. | No Pydantic/runtime instrumentation dependency; strict JSON plus caller-chosen validators and no telemetry. |
| Microsoft AutoGen | Conversational agents, teams, tools, streaming, memory, and save/load state. | Multi-agent team patterns and a broader event/message ecosystem. | Intentionally avoids a team framework; bounded sequential orchestration and a narrow provider seam. |

Official sources:

- [OpenAI Agents SDK overview](https://openai.github.io/openai-agents-python/),
  [tools](https://openai.github.io/openai-agents-python/tools/), and
  [running agents](https://openai.github.io/openai-agents-python/running_agents/)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence),
  [human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop),
  and [streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming)
- [Pydantic AI overview](https://pydantic.dev/docs/ai/overview/)
- [AutoGen agents](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html),
  [teams](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html),
  [memory](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/memory.html),
  and [state](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/tutorial/state.html)
- [OpenAI Chat Completions tool contract](https://platform.openai.com/docs/api-reference/chat)

## Decisions this comparison drives

Build and maintain:

- protocol conformance and adversarial bounds;
- small provider-neutral models and a documented custom-provider seam;
- local audit/guardrail/session/tool primitives that compose with ordinary Python;
- runnable internal-automation examples and a reproducible package/release path.

Do not chase by default:

- a proprietary graph language;
- dozens of native provider adapters in the core package;
- hosted traces, eval dashboards, identity, billing, or secret storage;
- automatic provider fallback that can silently change cost or data destination;
- automatic execution of model-authored code.

## Evidence still needed for market credibility

The source package can be credible before it is commercially proven. The next
external evidence should be:

1. a consumer-owned compatibility test from one real Samsarix application;
2. a live smoke matrix against at least one hosted and one local compatible
   endpoint, using non-sensitive fixtures and explicit spend caps;
3. exact-head GitHub CI across Python 3.11-3.14;
4. owner-approved historical provenance and PyPI Trusted Publishing setup;
5. installation and version evidence from the published wheel.

Until those exist, documentation should say "alpha" and distinguish deterministic
protocol tests from live-provider proof.
