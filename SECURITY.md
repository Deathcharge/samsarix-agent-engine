# Security policy

## Supported surface

The supported product surface is the Python package under
`src/samsarix_agent_engine/` and the `samsarix-agent` CLI. Version `0.1.x` is alpha;
there is not yet a published, production-supported release.

Historical `agents/` and `services/` extracts are absent from the current tree and
distributions. Findings against older revisions do not describe the supported
package unless an actual current package path reaches the affected code.

## Trust boundaries and invariants

- Prompts, system prompts, session identifiers, provider responses, and model
  output are untrusted data.
- Provider objects, model identifiers, API base URLs, environment variables, and
  request limits are trusted developer/operator configuration. Applications that
  expose them to end users create an additional boundary and must constrain it.
- API credentials must enter through environment/configuration, must not appear in
  URLs, logs, exceptions, command-line arguments, or persisted history.
- Sanitized exception wrappers must suppress secret-bearing causes in ordinary
  formatted tracebacks. Applications must not log raw exception context or frame
  locals; suppression is not memory erasure. Trusted custom providers are
  responsible for sanitizing public SDK errors they raise directly.
- The engine must never execute model output or silently select a different paid
  provider.
- Every network request must be bounded by time, retry count, response size, and
  cancellation. Redirects are disabled by default.
- Conversation, audit-event, and metrics state must remain bounded and process-local.
  Portable session snapshots are created only through an explicit call, do not copy
  provider configuration, and are size/version/schema checked. Their conversation
  text can contain sensitive data, including secrets supplied in prompts/responses.
  The calling application owns redaction, encryption, retention, access control,
  and storage.
- Audit events must not contain prompt, response, system-prompt, or credential
  content. Tool-event metadata must be locally generated or selected from the
  registered tool set, never copied from provider-selected call identifiers or
  unavailable tool names. Callers must use nonsecret agent/session/provider/model
  identifiers because these identifiers are retained in event metadata.
- Strict JSON parsing must bound raw input before decoding, including direct calls
  to the exported parser, and reject rather than truncate oversized values.
- Complete-output guardrails must fail closed for streaming rather than expose
  content before inspection.
- Tool definitions and handlers are trusted local application code. Model-selected
  tool names and arguments are untrusted; arguments must remain bounded strict JSON,
  and each handler must validate its own fields before any effect.
- Effectful tools require explicit caller-owned approval by default. A tool must not
  execute when approval is absent or denied, or when insufficient request, round,
  or call budget remains to obtain the final model response.
- Tool results are sent to the explicitly configured model provider. Handlers must
  minimize and redact results, never return credentials, and use application-owned
  idempotency and recovery for effects that cannot be rolled back.
- Multi-agent orchestration must have a hard call-amplification limit.

## Reporting

Use the repository's GitHub Security Advisory interface when it is enabled, or
email support@samsarix.com with `[SECURITY]` in the subject. Do not include exploit
details, private user content, or secrets in a public issue.

Include the affected version or commit, the smallest reproducer, impact, required
preconditions, and whether a real credential or external service was involved.
Never submit live credentials or private user content.
