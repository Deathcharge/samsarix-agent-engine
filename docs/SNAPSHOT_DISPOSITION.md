# Historical snapshot disposition

This record explains exactly what Agent Engine PR #4 removes, what the supported
package retains, and when the removal would be a regression.

## Decision summary

The removal is **not a regression for the installable `samsarix-agent-engine`
package or its documented API**. It is an intentional repository-boundary change.
It **is a breaking change for an undocumented checkout-only workflow** if a consumer
adds this repository root to `PYTHONPATH` and imports the historical top-level
`agents` or `services` packages.

That checkout-only workflow is not supportable from this repository: it can resolve
private `apps.backend.*` modules from another checkout, depends on a large undeclared
application stack, is absent from wheel and sdist artifacts, and has no tests here.
Consumers that need an application capability must use its owning application's
public contract rather than rely on these copies.

## Exact scope

Commit `3b3961d4ec1416f19e5f102d865d5664f43e27a9` removes exactly 160 tracked paths:

- 20 files under `agents/` (18 Python and two JSON data files), 533,962 bytes;
- 140 files under `services/` (136 Python plus SQL, Markdown, shell, and text
  artifacts), 2,807,748 bytes;
- 154 Python files and 3,325,736 Python-source bytes in total.

The exact path ledger is [REMOVED_SNAPSHOT_FILES.md](REMOVED_SNAPSHOT_FILES.md).
The files were added together in commit `99084aa73052de8993208550fbf5e18475ffd628`
on 2026-03-28 and were never part of the `src/samsarix_agent_engine` package.

## What the snapshot contains

The filename and source inventory spans much more than an agent SDK:

| Area | Representative removed material | Disposition |
|---|---|---|
| Agent catalog and personas | registry, profiles, personality tiers, named agents, visual builder, collective loops | Historical application material; not replaced as a catalog by this package. |
| Agent and team coordination | coordinators, protocols, communication logging, team templates, selection, multi-agent orchestration | Only a small bounded sequential `AgentOrchestrator` is supported here; the broader coordination system is not replaced. |
| Model and retrieval services | LLM bridge/router, unified/local LLM, RAG, vector search, web search, knowledge extraction, voice, code agents | Outside Agent Engine. Provider routing and retrieval belong behind versioned adapters or their owning packages. |
| Workflow and distributed execution | workflow engines/connectors/validators, durable execution, worker queue, background tasks, event bus, dead-letter queue | Not replaced. Agent Engine deliberately does not claim durable or distributed workflows. |
| Application infrastructure | API gateway, WebSockets, service registry, internal clients, storage/cache/database, backups, Backblaze, Nextcloud, Notion, GitHub | Not an SDK responsibility and not shipped here. |
| SaaS business systems | billing, credits, coupons, subscriptions, tax, usage, trials, onboarding, engagement, email, templates | Not replaced; these require application-owned identity, data, and operational contracts. |
| Security, identity, and privacy | admin bypass, OAuth, MFA, policy middleware/defaults, proprietary auth, GDPR service | Not replaced. Importing these copies as authority would be unsafe; security ownership must remain with the application. |
| Evaluation and operations | metrics, monitoring, performance analytics, tracing, prediction, quality scoring, Sentry | Agent Engine retains only bounded content-free local events and basic metrics, not this observability stack. |
| Collaboration and content | canvas, annotations, feedback, living documents, helpdesk, marketplace, collaboration threads | Product/application features, not Agent Engine APIs. |

## What the supported package retains or adds

PR #4 retains a deliberately narrow, tested surface under
`src/samsarix_agent_engine/`:

- named prompt agents and bounded in-memory sessions;
- an explicit offline echo provider and an OpenAI-compatible HTTP provider;
- bounded retries, response sizes, streaming, request/session/history budgets, and
  sequential multi-agent fan-out;
- strict JSON and caller-supplied structured-output validation;
- local input/output guardrails and content-free lifecycle events;
- versioned portable session snapshots with caller-owned persistence and encryption;
- approval-required-by-default function tools with hard round, call, argument,
  result, and remaining-request budgets;
- a CLI plus offline support-triage and operator-approved-action examples.

This is a replacement only for the narrow agent/session/provider slice. It does not
pretend to replace the snapshot's billing, identity, persistence, workflow,
integration, retrieval, or hosted application systems.

## Reproducible evidence

- `pyproject.toml` discovers only packages under `src/` whose name matches
  `samsarix_agent_engine*`.
- `MANIFEST.in` pruned `agents` and `services` before their removal.
- Building parent commit `c709e2b444a21fc7eaaa9ef8afaf5f1cea4b040a`
  produced a wheel and sdist containing zero snapshot entries.
- No supported `src/`, test, example, or other root file imports top-level
  `agents` or `services`.
- 100 of the 154 removed Python files contain `apps.backend` references. The
  snapshot also contains hundreds of imports from undeclared databases, queues,
  web frameworks, provider SDKs, storage systems, and observability libraries.
- A checkout import probe resolved `apps.backend` from an external application
  checkout and triggered configuration/security initialization side effects. That
  proves the old import path was environment-dependent rather than standalone.
- A scan of the other 39 recorded local non-flagship repositories found no consumer
  importing these top-level snapshot packages. Hits referred either to an unrelated
  third-party `agents` package or directly to canonical `apps.backend.*` paths.

## Recovery and rollback

- Last branch commit before removal:
  `c709e2b444a21fc7eaaa9ef8afaf5f1cea4b040a`.
- Removal commit: `3b3961d4ec1416f19e5f102d865d5664f43e27a9`.
- Annotated remote archive tag:
  `archive/pre-agent-engine-snapshot-removal-20260810`.
- Inspect without restoring:
  `git ls-tree -r --name-only archive/pre-agent-engine-snapshot-removal-20260810 -- agents services`.
- Extract for archaeology into a new, non-product directory:
  `git archive archive/pre-agent-engine-snapshot-removal-20260810 agents services`.

Do not restore the directories to the supported package merely to preserve history.
If a removed capability is still valuable, identify its canonical owner, define a
public versioned contract, and migrate or reimplement it with its real dependencies,
security boundary, tests, and operating model.

## Merge gate

The snapshot deletion is acceptable only if all of the following remain true:

1. the exact file manifest and pre-removal archive ref remain available remotely;
2. package artifact checks continue rejecting accidental snapshot inclusion;
3. exact-head CI and an independent review approve the full PR, including the
   supported runtime additions rather than only this deletion;
4. the owner accepts Agent Engine as a narrow OpenAI-compatible session/provider
   client, not a second general-purpose runtime competing with Agent Framework;
5. merge is not presented as publication or adoption approval.
