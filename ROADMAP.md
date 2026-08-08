# Samsarix Agent Engine roadmap

This roadmap separates four gates: merge, release, publication, and flagship adoption. Passing one does not imply the next.

## Product boundary

Portfolio role: **reusable library or sdk**. Keep this as a small, independently versioned package. Samsarix Unified should consume it only through a public API adapter; private monorepo imports and copied implementations are out of scope.
Repository identity: `Deathcharge/samsarix-agent-engine` (renamed 2026-07-29;
consolidation candidate).

Current disposition: Keep the productized default stable while testing whether this
bounded runtime earns a canonical role before any consolidation or publication.

## Stabilize the productized default

- Keep the default branch buildable from a clean checkout and preserve exact-head CI evidence.
- Keep Samsarix LLC branding, package identity, license metadata, and compatibility aliases internally consistent.
- Preserve the pre-productization default under a rollback ref before merging; do not delete legacy history.
- Locally reproduced in this pass: formatting, lint, types, Bandit, coverage tests, and package build pass.
- Next: choose whether Agent Engine or another adjacent SDK owns the canonical provider/runtime abstraction, then consolidate.
- Review priority: Choose canonical portfolio agent SDK.
- Review priority: prove one consumer/live endpoint.
- Review priority: approve MPL/provenance.
- Review priority: isolate legacy through owner-approved cleanup or freeze publication.

## Release candidate

- Build and install the wheel in a clean environment.
- Prove one real consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

Current hardening backlog:

- 160 legacy files remain in the checkout; 153 are exact current flagship duplicates, creating audit, license, and contributor confusion.
- No proven downstream consumer or live compatible-endpoint smoke test.
- Strong functional overlap with flagship and other portfolio LLM/agent packages weakens differentiation.
- Package name/PyPI trusted publisher and actual CI success are unverified.
- Built-in durable storage, resumable or rollback-capable tool workflows, multiple
  native provider protocols, and parallel turns remain absent; portable session
  snapshots, bounded native streaming, and approval-gated function tools now cover
  the smallest persistence, interactive-output, and safe-action seams.
- License transition and provenance are unresolved.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
