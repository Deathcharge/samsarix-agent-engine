# Changelog

All notable changes will be documented here. The project uses semantic versioning
once releases begin.

## 0.1.0 - Unreleased

### Added

- Standalone `src/` package with a deliberate public API.
- Bounded in-memory agents and sequential orchestration.
- Deterministic offline echo provider.
- Bounded OpenAI-compatible HTTP provider.
- Native bounded SSE streaming with a compatibility fallback for custom providers.
- Strict JSON parsing and caller-defined structured-output validation that avoid
  committing invalid model responses to session history.
- Non-interactive CLI with JSON output and meaningful exit codes.
- CLI streaming and strict structured-output modes.
- Synchronous input/output guardrails with fail-closed streaming semantics when
  complete-output inspection is configured.
- Bounded, content-free local lifecycle events for requests, guardrails, and
  session import/export operations.
- Strict, versioned, size-bounded session snapshots for application-managed
  persistence without credential or file-I/O coupling.
- Opt-in OpenAI-compatible function tools with strict JSON argument parsing,
  sequential execution, approval required by default, and hard model-round,
  request, call, argument, and result limits.
- Content-free tool request/approval/denial/success/failure audit events and
  dedicated sanitized approval/execution error contracts.
- Real unit, integration, packaging, lint, type, and security checks.
- Productization, security, legacy-boundary, setup, and release documentation.
- Samsarix package, import, CLI, environment-variable, and company branding.
- MPL-2.0 licensing, source notices, trademark guidance, and citation metadata.
- PEP 561 `py.typed` marker for downstream type checkers.
- Environment-protected PyPI Trusted Publishing workflow with isolated build and
  publish jobs, artifact guards, tag/version matching, and no long-lived token.

### Removed

- Orphaned root LLM modules that required private `helix-unified` imports.
- Mock-only tests and examples for APIs that did not exist.
- Unverifiable model-pricing, free-credit, and production-readiness claims.
- Contradictory BSL/proprietary license files for the current source tree.
