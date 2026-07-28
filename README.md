# Helix LLM Agent Engine

Helix LLM Agent Engine is a small Python SDK and CLI for running named, stateful
prompt agents against an OpenAI-compatible chat endpoint. It is for developers
who need a thin, auditable agent/session layer without adopting a tool graph,
hosted control plane, database, or multi-provider gateway.

The package is currently **alpha quality**. Its offline path is usable for local
evaluation; publication is intentionally blocked until the owner resolves the
repository's license metadata. See [Productization](docs/PRODUCTIZATION.md).

## What it does

- Creates named agents with a model and system prompt.
- Keeps bounded, in-memory conversation history per session.
- Enforces input, response, history, session, output-token, retry, and request-count limits.
- Calls one OpenAI-compatible `chat/completions` endpoint with bounded retries,
  timeouts, response size, and no redirect following.
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
helix-agent run "installation complete"
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

from helix_llm_agent_engine import LLMAgentEngine


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

The public API is exported from `helix_llm_agent_engine`: `LLMAgentEngine`,
`Agent`, `AgentOrchestrator`, `BaseLLMProvider`, `EchoProvider`,
`OpenAICompatibleProvider`, `ChatMessage`, `ProviderResponse`, and the documented
exception classes.

## OpenAI-compatible endpoint

Pass secrets through an environment variable, never a command-line argument:

```bash
export OPENAI_API_KEY="replace-me"  # PowerShell: $env:OPENAI_API_KEY="replace-me"
helix-agent run "Summarize this release" \
  --provider openai \
  --model your-model-id
```

For a local or third-party compatible service:

```bash
helix-agent run "health check" \
  --provider openai \
  --model your-model-id \
  --base-url http://127.0.0.1:8000/v1 \
  --json
```

`--base-url` is trusted developer/operator configuration. The client accepts only
absolute HTTP(S) URLs without embedded credentials, query strings, or fragments.
It does not follow redirects. Applications that let end users select this value
must add their own destination allowlist and network egress controls.

Use `helix-agent --help` and `helix-agent run --help` for every option. Exit code
`2` means invalid input/configuration, `3` means provider failure, and `130` means
the user cancelled the command.

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
python -m mypy src/helix_llm_agent_engine
python -m bandit -r src/helix_llm_agent_engine -q
python -m pip_audit -r requirements.txt
python -m pytest --cov=helix_llm_agent_engine --cov-report=term-missing
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
- Only non-streaming OpenAI-compatible chat completions are built in.
- No persistent history, tool execution, structured output, provider-specific
  Anthropic support, token estimation, or automatic fallback.
- The repository contains historical backend extracts that depend on private
  `helix-unified` modules and are not part of this product.
- Package publication is blocked pending owner confirmation of package name,
  licensing text, and publishing identity.

## Contributing and license status

See [CONTRIBUTING.md](CONTRIBUTING.md) for the verified development workflow and
[CHANGELOG.md](CHANGELOG.md) for release changes.

The root `LICENSE` identifies Business Source License 1.1, but its Licensed Work
name and timing terms do not clearly identify this repository. It conflicts with
claims in `LICENSE.PROPRIETARY`. No SPDX license is asserted in package metadata,
and the package has a `Private :: Do Not Upload` classifier until the owner makes
and documents the legal decision. Do not treat this README as legal advice or as
a grant beyond the repository's license files.
