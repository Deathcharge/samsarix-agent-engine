# Getting started

This guide exercises the complete supported path: install the package, run an
offline agent, inspect session state, then optionally configure a network model.

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
helix-agent --version
helix-agent run "hello"
helix-agent run "hello" --json
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
helix-agent run "hello" --provider openai --model your-model-id
```

Use `--base-url` for an explicitly trusted local or third-party compatible
endpoint. The configured base URL is extended with `/chat/completions` unless it
already ends with that path.

The CLI never accepts an API key value as an argument. Change the environment
variable name with `--api-key-env` when needed.

## 5. Handle ordinary failures

- Empty and oversized prompts fail before a provider call.
- A missing model or required OpenAI credential exits with status `2`.
- Timeouts, connection failures, malformed responses, and HTTP errors exit with
  status `3`.
- Retryable failures use a bounded exponential delay and at most five configured
  retries.
- Exceeding a session request budget raises `BudgetExceededError`; call
  `agent.clear_history(session_id)` only when an explicit reset is appropriate.

See `examples/custom_llm_provider.py`, `examples/error_handling.py`, and
`examples/multi_agent_collaboration.py` for additional runnable behavior.
