# Samsarix Agent Engine

Samsarix Agent Engine is a small Python SDK and CLI for running named, stateful
prompt agents against an OpenAI-compatible chat endpoint. It is for developers
who need a thin, auditable agent/session layer without adopting a tool graph,
hosted control plane, database, or multi-provider gateway.

The package is currently **alpha quality**. Its offline path is usable for local
evaluation, and its release process remains gated on protected PyPI publishing and
CI verification. See [Productization](docs/PRODUCTIZATION.md).

## What it does

- Creates named agents with a model and system prompt.
- Keeps bounded, in-memory conversation history per session.
- Enforces input, response, history, session, output-token, retry, and request-count limits.
- Calls one OpenAI-compatible `chat/completions` endpoint with bounded retries,
  timeouts, response size, and no redirect following.
- Streams bounded text deltas from compatible SSE endpoints, with an invocation
  fallback for existing custom providers.
- Parses strict JSON and supports caller-defined structured-output validation
  without requiring Pydantic or another runtime dependency.
- Runs explicit local input/output guardrails and retains bounded content-free
  lifecycle events for audit integrations.
- Exports and imports strict, versioned session snapshots while leaving storage,
  encryption, and retention policy to the application.
- Supports custom providers through a four-argument async interface.
- Includes an explicit deterministic `EchoProvider` so setup can be evaluated
  without credentials, network access, or API cost.
- Exposes meaningful CLI exit codes and JSON output for automation.

It does not execute tools, persist conversations, provide authentication, host an
API, estimate provider bills, or silently fall back to another paid provider.

## Fastest successful setup

Prerequisites: Python 3.11 or newer and `pip`.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
samsarix-agent run "installation complete"
```

Expected output:

```text
Echo: installation complete
```

`EchoProvider` is a setup/test double, not an LLM. Run the complete offline
example with `python examples/basic_agent.py`.

## Python API

```python
import asyncio

from samsarix_agent_engine import LLMAgentEngine


async def main() -> None:
    engine = LLMAgentEngine(max_requests_per_session=10)
    agent = engine.create_agent(
        name="assistant",
        model="echo",
        system_prompt="Be concise.",
    )
    print(await agent.invoke("hello", session_id="demo"))
    print(agent.get_metrics())
    await engine.close()


asyncio.run(main())
```

Stream a response while retaining history only after the stream completes:

```python
async for delta in agent.stream("Draft a short release note", session_id="demo"):
    print(delta, end="", flush=True)
```

Require strict JSON, then validate it into an application type:

```python
from dataclasses import dataclass

from samsarix_agent_engine import JsonValue


@dataclass(frozen=True)
class TicketRoute:
    queue: str
    priority: int


def validate_route(value: JsonValue) -> TicketRoute:
    if not isinstance(value, dict):
        raise ValueError("expected an object")
    queue = value.get("queue")
    priority = value.get("priority")
    if not isinstance(queue, str):
        raise ValueError("queue must be a string")
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ValueError("priority must be an integer")
    return TicketRoute(queue=queue, priority=priority)


route = await agent.invoke_structured(
    'Return only JSON like {"queue":"billing","priority":2}',
    validate_route,
)
```

Invalid JSON or validator failures raise `StructuredOutputError`, count as failed
requests, and are not added to conversation history. The validator runs once and
the SDK does not automatically retry or repair model output.

## Guardrails, events, and portable sessions

Guardrails are synchronous local callables. Input guardrails run before request
budget is consumed or a provider is called. Output guardrails run after the paid
response is received but before it enters history:

```python
from samsarix_agent_engine import GuardrailContext, GuardrailResult


def reject_secrets(text: str, context: GuardrailContext) -> GuardrailResult:
    if "private-key" in text.lower():
        return GuardrailResult(allowed=False, reason=f"blocked {context.stage}")
    return GuardrailResult(allowed=True)


agent = engine.create_agent(
    name="support-router",
    model="echo",
    input_guardrails=(reject_secrets,),
    output_guardrails=(reject_secrets,),
)
```

Output guardrails require the complete response. `agent.stream()` therefore fails
closed when any output guardrail is configured; use `invoke()` for that agent.
Guardrail callback failures are sanitized, explicit blocks raise `GuardrailError`,
and CLI exit code `4` distinguishes them from provider failures.

`agent.events()` returns a bounded local trail containing event type, timestamp,
agent/session/provider/model identifiers, request number, latency, and error type.
Events deliberately omit prompt, response, system-prompt, and credential content.

Portable sessions use application-managed storage rather than hidden SDK I/O:

```python
from samsarix_agent_engine import SessionSnapshot


snapshot = await agent.export_session("customer-42")
serialized = snapshot.to_json()  # store/encrypt according to your policy

restored = SessionSnapshot.from_json(serialized)
await agent.import_session(restored, session_id="customer-42-restored")
```

Snapshots are strict, versioned, limited to 1,000 messages and 1,000,000 serialized
characters, contain successful user/assistant turns plus the consumed request
count, and never contain API credentials. They are not encrypted by the SDK.

The public API is exported from `samsarix_agent_engine`: `LLMAgentEngine`,
`Agent`, `AgentOrchestrator`, `BaseLLMProvider`, `EchoProvider`,
`OpenAICompatibleProvider`, `ChatMessage`, `ProviderResponse`,
`ProviderStreamChunk`, `JsonValue`, `parse_json_output`, and the documented exception
classes, guardrail/event models, and `SessionSnapshot`.

## OpenAI-compatible endpoint

Pass secrets through an environment variable, never a command-line argument:

```bash
export OPENAI_API_KEY="replace-me"  # PowerShell: $env:OPENAI_API_KEY="replace-me"
samsarix-agent run "Summarize this release" \
  --provider openai \
  --model your-model-id
```

For a local or third-party compatible service:

```bash
samsarix-agent run "health check" \
  --provider openai \
  --model your-model-id \
  --base-url http://127.0.0.1:8000/v1 \
  --json
```

Use `--stream` for live text or `--expect-json` to reject a non-JSON response and
write only the parsed JSON value. These output modes are mutually exclusive.

`--base-url` is trusted developer/operator configuration. The client accepts only
absolute HTTP(S) URLs without embedded credentials, query strings, or fragments.
It does not follow redirects. Applications that let end users select this value
must add their own destination allowlist and network egress controls.

Use `samsarix-agent --help` and `samsarix-agent run --help` for every option. Exit
code `2` means invalid input/configuration, `3` means provider failure, `4` means a
guardrail blocked or failed, and `130` means the user cancelled the command.

## Configuration and cost controls

The engine defaults to 20 retained history messages, 100 sessions, 20,000 input
characters, 1,024 requested output tokens, and 100 requests per session. The
default retained response limit is 200,000 characters. The OpenAI-compatible
provider defaults to a 30-second timeout, two retries, no
redirects, and a 2 MB response cap. All limits are configurable within guarded
ranges.

These are local safety limits, not provider quotas. A two-agent, three-iteration
orchestration performs six provider calls. The maximum built-in orchestration is
8 agents × 5 iterations = 40 calls. Confirm model pricing and enforce provider
account budgets before using paid endpoints.

## Development

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src/samsarix_agent_engine
python -m bandit -r src/samsarix_agent_engine -q
python -m pip_audit -r requirements.txt
python -m pytest --cov=samsarix_agent_engine --cov-report=term-missing
python -m build
python -m twine check dist/*
```

The CI workflow is configured to run the same product checks on Python 3.11–3.14
and verify wheel/sdist contents. The large `agents/` and `services/` directories are preserved legacy
extractions and are not installed or covered by release claims; see
[Legacy code](docs/LEGACY_CODE.md).

## Architecture

```text
CLI / application
      |
LLMAgentEngine -- provider registry and bounded defaults
      |
Agent ---------- validated input, session history, metrics, request budget
      |
BaseLLMProvider
      +-- EchoProvider (offline setup/test double)
      +-- OpenAICompatibleProvider (bounded HTTP client)
      +-- application-defined provider
```

Conversation state is process-local and is lost on restart. Each `Agent`
serializes its own invocations so turns cannot be reordered; use separate agents
for independent concurrency.

## Security and privacy

- Prompts and responses are sent only to the provider explicitly selected by the
  caller. Echo mode makes no network request.
- The package does not log prompts, responses, or API keys.
- HTTP error messages omit response bodies and transport exception text.
- No telemetry is collected.
- Conversation history remains in memory until evicted or cleared.
- Model output is untrusted data; this package never executes it.
- Plain-text CLI output replaces terminal control characters; JSON mode escapes them.

Read [SECURITY.md](SECURITY.md) for trust boundaries and reporting guidance.

## Maturity and limitations

- Alpha: the API may change before `1.0`.
- Only OpenAI-compatible chat completions are built in; streaming requires an SSE
  implementation compatible with that protocol.
- No built-in database/storage adapter, tool execution, provider-specific Anthropic
  support, token estimation, automatic output repair, or automatic provider fallback.
- The repository contains historical backend extracts that depend on private
  `helix-unified` modules and are not part of this product.
- The GitHub repository, distribution, and import namespace use Samsarix branding.
  GitHub redirects the historical `helix-hub-shared` repository URL for compatibility.

## Contributing and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the verified development workflow and
[CHANGELOG.md](CHANGELOG.md) for release changes.

The current source tree is licensed under the Mozilla Public License 2.0. Modified
covered files stay under MPL-2.0 when distributed, while a larger application may
license its separate files differently. See [LICENSING.md](LICENSING.md),
[NOTICE](NOTICE), and [TRADEMARKS.md](TRADEMARKS.md). General questions can go to
contact@samsarix.com and product support to support@samsarix.com.
