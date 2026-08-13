# Practical use cases

Samsarix Agent Engine fits internal Python applications that already control an
OpenAI-compatible endpoint and want a small, inspectable runtime around model
calls. It is strongest when a full graph framework, hosted trace service, or broad
provider gateway would add more operational surface than value.

## 1. Support-ticket triage

Use `invoke_structured()` to turn a free-text ticket into a validated queue,
priority, and summary. Input/output guardrails can reject credential-like content,
content-free events provide operational evidence, and a session snapshot can move
successful context into application-owned encrypted storage.

Runnable proof:

```bash
python examples/support_triage.py
```

Application responsibilities:

- prompt the real model to return only the expected object;
- validate every field and enum before updating a ticket system;
- keep ticket/user identifiers out of logs when policy requires it;
- encrypt snapshots and enforce retention outside the SDK.

## 2. Operator-approved support actions

Use `run_tools()` when a model may propose a named action but an authenticated
operator or policy engine must approve it before execution. Approval is required by
default, model arguments must be bounded strict JSON objects, handlers execute
sequentially, and the model-call/tool-call amplification is capped.

Runnable proof (the effect is an in-memory ticket transition):

```bash
python examples/approved_support_action.py
```

Application responsibilities:

- validate every tool argument inside the handler even when strict schemas are
  requested from the provider;
- make effectful handlers idempotent and record application-level idempotency keys;
- authenticate the human or policy service behind the approval callback;
- return only a minimal redacted tool result because that JSON is sent to the
  configured model provider;
- own compensation/recovery if a later model call fails after an effect succeeds.

## 3. Interactive internal copilots

Use `agent.stream()` for a terminal, desktop, or web UI that should display text as
it arrives. The OpenAI-compatible SSE parser enforces a byte cap, the agent enforces
an aggregate response-character cap, and incomplete/cancelled streams do not enter
history. Existing custom providers inherit a complete-response fallback.

Use a separate non-streaming agent when complete-output guardrails are mandatory;
streaming fails closed rather than expose text before that inspection.

## 4. Batch classification and extraction

Use `invoke_json()` or `invoke_structured()` in a worker that processes bounded
records one at a time. Strict parsing rejects duplicate object keys, non-finite
numbers, excessive nesting, invalid Unicode surrogates, and invalid caller-defined
types. Invalid results consume the provider request but do not contaminate session
history.

The CLI supports `--expect-json` for shell automation and emits only the parsed JSON
value. It does not repair or retry invalid output automatically; the caller owns
retry policy and cost amplification.

## 5. Local-model and private-gateway front ends

Point `OpenAICompatibleProvider` at an explicitly trusted HTTP(S) base URL for a
local inference server or organization gateway. The client uses no vendor SDK,
follows no redirects, bounds timeout/retry/response size, omits response bodies and
raw transport messages from errors, and never falls back to another paid provider.

Applications that accept a base URL from an end user must add a destination
allowlist and network egress controls. The SDK treats the base URL as trusted
operator configuration and is not an SSRF firewall.

## Poor fits

Choose a different foundation when the requirement is primarily:

- durable multi-hour workflows with crash-safe checkpoints and resumable approval;
- graph/state-machine composition with dynamic branching;
- broad native provider routing, fallback, spend aggregation, or model translation;
- a hosted control plane, trace UI, tenant authentication, or billing;
- sandboxed execution of model-authored code or arbitrary user tools;
- parallel high-throughput turns within one ordered agent instance.

Those are deliberate product boundaries, not hidden roadmap promises.
