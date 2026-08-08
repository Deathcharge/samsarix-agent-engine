# Getting started

This guide exercises the supported path: install the package, run an offline
agent, inspect session state, try deterministic real-use-case fixtures, then
optionally configure a network model.

## 1. Create an isolated environment

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## 2. Verify the CLI without credentials

```bash
samsarix-agent --version
samsarix-agent run "hello"
samsarix-agent run "hello" --json
```

Expected text output is `Echo: hello`. JSON output includes the selected provider,
model, and local metrics. Echo mode never makes a network request.

## 3. Verify the Python journey

```bash
python examples/basic_agent.py
```

Expected output:

```text
Echo: installation complete
history_messages=2
successful_requests=1
```

## 4. Use a compatible endpoint (optional)

```bash
export OPENAI_API_KEY="replace-me"
samsarix-agent run "hello" --provider openai --model your-model-id
```

Use `--base-url` for an explicitly trusted local or third-party compatible
endpoint. The configured base URL is extended with `/chat/completions` unless it
already ends with that path.

The CLI never accepts an API key value as an argument. Change the environment
variable name with `--api-key-env` when needed.

For live text, add `--stream`. To require strict JSON and emit only the parsed
value, add `--expect-json`. `--stream`, `--expect-json`, and the JSON result
envelope (`--json`) are mutually exclusive.

## 5. Run the offline use-case proofs

```bash
python examples/support_triage.py
python examples/approved_support_action.py
```

The first demonstrates strict structured output, field validation, guardrails,
content-free events, and a portable session snapshot. The second demonstrates the
OpenAI-compatible function-tool transcript, default-required approval, an
idempotent in-memory action, model/tool budgets, and content-free tool events.
Both use deterministic local providers and make no network request.

## 6. Handle ordinary failures

- Empty and oversized prompts fail before a provider call.
- A missing model or required OpenAI credential exits with status `2`.
- Timeouts, connection failures, malformed responses, and HTTP errors exit with
  status `3`.
- Retryable failures use a bounded exponential delay and at most five configured
  retries.
- Exceeding a session request budget raises `BudgetExceededError`; call
  `agent.clear_history(session_id)` only when an explicit reset is appropriate.
- Invalid structured output raises `StructuredOutputError` and is not committed to
  history.
- A guardrail block raises `GuardrailError`; complete-output guardrails deliberately
  disable streaming for that agent.
- Missing or denied tool approval raises `ToolApprovalError` before the handler
  executes. Invalid arguments/results or sanitized handler failures raise
  `ToolExecutionError`.

See `examples/custom_llm_provider.py`, `examples/error_handling.py`, and
`examples/multi_agent_collaboration.py` for additional runnable behavior. Read
[Practical use cases](USE_CASES.md) for application responsibilities and
[Competitive position](COMPETITIVE_POSITION.md) for deliberate product boundaries.
