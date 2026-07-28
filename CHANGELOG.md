# Changelog

All notable changes will be documented here. The project uses semantic versioning
once releases begin.

## 0.1.0 - Unreleased

### Added

- Standalone `src/` package with a deliberate public API.
- Bounded in-memory agents and sequential orchestration.
- Deterministic offline echo provider.
- Bounded OpenAI-compatible HTTP provider.
- Non-interactive CLI with JSON output and meaningful exit codes.
- Real unit, integration, packaging, lint, type, and security checks.
- Productization, security, legacy-boundary, setup, and release documentation.

### Removed

- Orphaned root LLM modules that required private `helix-unified` imports.
- Mock-only tests and examples for APIs that did not exist.
- Unverifiable model-pricing, free-credit, and production-readiness claims.
