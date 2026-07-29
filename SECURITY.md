# Security policy

## Supported surface

The supported product surface is the Python package under
`src/samsarix_agent_engine/` and the `samsarix-agent` CLI. Version `0.1.x` is alpha;
there is not yet a published, production-supported release.

The root `agents/` and `services/` directories are preserved legacy extracts, are
not distributed, and should not be deployed from this repository. Security issues
in those files may still be useful portfolio cleanup reports, but they do not
describe the supported package unless an actual package path reaches them.

## Trust boundaries and invariants

- Prompts, system prompts, session identifiers, provider responses, and model
  output are untrusted data.
- Provider objects, model identifiers, API base URLs, environment variables, and
  request limits are trusted developer/operator configuration. Applications that
  expose them to end users create an additional boundary and must constrain it.
- API credentials must enter through environment/configuration, must not appear in
  URLs, logs, exceptions, command-line arguments, or persisted history.
- The engine must never execute model output or silently select a different paid
  provider.
- Every network request must be bounded by time, retry count, response size, and
  cancellation. Redirects are disabled by default.
- Conversation and metrics state must remain bounded and process-local unless a
  future explicit persistence feature defines stronger privacy controls.
- Multi-agent orchestration must have a hard call-amplification limit.

## Reporting

Use the repository's GitHub Security Advisory interface when it is enabled, or
email support@samsarix.com with `[SECURITY]` in the subject. Do not include exploit
details, private user content, or secrets in a public issue.

Include the affected version or commit, the smallest reproducer, impact, required
preconditions, and whether a real credential or external service was involved.
Never submit live credentials or private user content.
