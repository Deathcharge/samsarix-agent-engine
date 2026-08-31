# Productization record

Last updated: 2026-08-31

## Current repository assessment

The repository arrived as an inconsistent extraction from a larger Helix codebase.
Its strongest repeated intent was a Python distribution named
`helix-llm-agent-engine`, but that import package did not exist. The root engine,
gateway, and client modules imported private `apps.backend.*` or missing relative
modules. The much larger `agents/` and `services/` trees also depend on the
`helix-unified` application, undeclared databases, queues, web frameworks, and
deployment state.

The clean starting worktree was `main` at `2d6889b`, matching `origin/main`, with
no untracked files or alternate local branches. Recent history consisted mainly of
documentation, licensing, examples, and mock-test additions.

## Chosen product

Samsarix Agent Engine is a deliberately small Python SDK and CLI for developers
who want named prompts, bounded sessions, streaming, strict structured output,
local guardrails/events, portable snapshots, and approval-aware function tools over
an OpenAI-compatible endpoint.

The primary use case is: install in an empty Python environment, create or run a
named agent, receive a response, continue a bounded session, inspect local metrics,
and recover clearly from invalid input or provider failure. The first-run journey
uses a deterministic offline echo provider so evaluation needs no credentials,
private repository, network, or API spend.

This product is independently useful as an auditable layer smaller than a complete
agent graph or provider gateway. It does not reproduce `helix-unified`.

## Target user and primary journey

Target user: a Python application developer who already controls an
OpenAI-compatible model endpoint and wants a thin agent/session abstraction with
safe operational defaults.

Primary journey:

1. Create a Python 3.11+ virtual environment.
2. Install the repository with `python -m pip install -e .`.
3. Run `samsarix-agent run "installation complete"` without credentials.
4. Receive `Echo: installation complete` and exit code 0.
5. Optionally set an API key, select a trusted base URL and model, and receive a
   normalized chat response or an actionable bounded error.

## Key product and architecture decisions

- Use modern `pyproject.toml` metadata and a `src/` package so tests exercise the
  installed package shape rather than accidental root imports.
- Include only `samsarix_agent_engine*` in distributions. The legacy backend
  snapshot was removed from the checkout and remains recoverable in Git history.
- Keep one required runtime dependency (`httpx`) and avoid vendor SDK coupling.
- Provide an abstract custom-provider seam rather than claiming broad provider
  support.
- Make echo an explicit test provider, never a hidden fallback after paid-provider
  failure.
- Keep live history in memory and bounded. Expose strict portable snapshots while
  leaving storage, encryption, access control, and retention to the application.
- Require approval for tools by default, parse model arguments as bounded strict
  JSON, execute sequentially, and refuse effects when no final-response request
  budget remains.
- Serialize calls per agent to preserve turn ordering. Independent agents can run
  concurrently.
- Bound prompt size, output request size, sessions, history, per-session requests,
  orchestration fan-out, timeout, retries, backoff, redirects, and response size.
- Do not log prompts, outputs, credentials, response bodies, or raw transport errors.
- Use the portfolio-consistent MPL-2.0 license with a company notice, source-file
  notices, separate trademark policy, and citation metadata.
- Keep public upload gated on protected publishing identity and release CI rather
  than on ambiguous source licensing.

## Assumptions

- Python 3.11 is the minimum supported version because the existing metadata already
  required it and the implementation uses current typing syntax.
- Model and base URL are trusted developer/operator configuration. A product that
  exposes them to end users must add allowlists and egress policy.
- Provider-reported usage is informational and may not equal billable usage.
- Existing grants on historical revisions remain governed by the license files
  shipped with those revisions; the current tree is MPL-2.0.

## Baseline command results

Commands were run on the original `2d6889b` worktree before implementation:

| Command | Actual result |
| --- | --- |
| `git status --short --branch` | Clean `main...origin/main`. |
| `python -m pytest` | Exit 0; 35 passed in 7.88s. Every test exercised fixtures or `MagicMock`, not implementation. |
| `python -m compileall -q .` | Exit 0. Syntax only. |
| `python setup.py --name && --version && check` | Reported `helix-llm-agent-engine` 1.0.0 with a deprecated false MIT classifier. |
| `python examples/basic_agent.py` | Exit 1: `ModuleNotFoundError: helix_llm_agent_engine`. |
| `python -c __import__('inference_client')` | Exit 1: relative import with no parent package. |
| root `llm_agent_engine` / `agents` imports | Appeared to import only because the workstation exposed `C:\Users\Andrew\Helix\helix-unified`; import logs proved the undocumented cross-repository dependency. |
| `python -m flake8 . ... --count` | Exit 1; 6,106 findings across the repository. |
| focused `python -m mypy ...` | Produced no result after several minutes in the shared environment and was terminated by exact PID. |
| `python -m black --check --diff ...` | Exit 1; 15 files would be reformatted. |
| `python -m pip check` | Exit 1 due unrelated conflicts in the shared global Python environment; clean-environment verification required. |

No GitHub Actions workflow, `pyproject.toml`, real package directory, release
changelog, security policy, `.env.example`, or coherent package tests existed.

## Findings and priorities

### P0

- [x] Advertised import package and CLI did not exist.
- [x] All examples failed at their first import.
- [x] Root implementations required another private repository.
- [x] Packaging installed broad `agents` and `services` snapshots with undeclared
  dependencies and a nonexistent console target.
- [x] Tests passed without exercising product code.
- [x] README claimed production readiness, MIT licensing, docs, CI, and developer
  files that did not exist.

### P1

- [x] Add bounded input, history, sessions, request counts, retries, backoff,
  response size, timeouts, cancellation propagation, and orchestration fan-out.
- [x] Prevent redirect following and credentials in provider URLs.
- [x] Sanitize provider/transport errors and avoid response-body logging.
- [x] Add real tests, lint, formatting, type checking, coverage, build checks, and CI.
- [x] Remove stale hard-coded provider pricing/free-credit/model claims.
- [x] Document legacy code as non-distributed rather than implying support.
- [x] Resolve contradictory license terms, legal identity, and working contacts.
- [x] Confirm the Samsarix distribution and import namespace.
- [ ] Register the PyPI project and configure Trusted Publishing (external gate).

### P2

- [x] Native streaming with bounded partial-response handling.
- [x] Optional structured-output validation.
- [x] Local guardrails, content-free lifecycle events, and portable snapshots.
- [x] Approval-aware bounded function tools with deterministic protocol tests.
- [ ] Provider-specific adapters as optional packages, only when demanded.
- [ ] Persistent session adapter with an explicit encryption/retention design.
- [ ] Prove a consumer-owned compatibility fixture and live endpoint smoke matrix.
- [x] Remove the preserved legacy snapshot after confirming canonical repositories
  and Git-history recovery.

## Implementation checklist

- [x] Modern `src/` package and stable public exports.
- [x] Offline provider and complete zero-credential setup path.
- [x] Bounded OpenAI-compatible provider.
- [x] Stateful agent, metrics, reset, and error contracts.
- [x] Bounded sequential multi-agent helper.
- [x] CLI help, version, stdout/stderr separation, JSON mode, and exit codes.
- [x] Real deterministic tests and package-content CI guard.
- [x] README, getting started, security, legacy, contributing, changelog, and release docs.
- [x] Record final isolated verification outcomes below.
- [x] Complete code-level adversarial review and regression verification.
- [ ] Seal the historical security workbench report (artifact-access limitation;
  not a completed scan or a substitute for the current verification below).

## Release acceptance criteria

- Empty-environment editable install and wheel install both work.
- `samsarix-agent --help`, `--version`, offline text, offline JSON, and stdin paths work.
- Lint, format, strict types, tests with at least 90% branch coverage, build, metadata,
  and package-content checks pass.
- No wheel/sdist contains `agents/` or `services/`.
- No locally actionable P0 remains on the supported product path.
- Documentation describes only verified behavior.
- Security scan covers the supported package and records legacy exclusions/gaps.
- Owner license and publishing gates are explicit before public distribution.

## Completed work

- Replaced the nonexistent package with a standalone implementation under `src/`.
- Replaced mock-only tests with implementation and protocol tests.
- Replaced fictional examples with offline, custom-provider, budget-error, and
  bounded-collaboration examples.
- Replaced `setup.py` with PEP 517/621 metadata and an explicit package allowlist.
- Added CI and current supported Python matrix.
- Rewrote user, contributor, security, legacy, and release documentation.
- Migrated the unreleased package, import namespace, CLI, environment variable,
  metadata, and policies from Helix to Samsarix branding.
- Adopted the unmodified MPL-2.0 with Samsarix LLC ownership/contact notices,
  trademark guidance, citation metadata, and PEP 561 typing metadata.
- Added an environment-protected, OIDC-based PyPI release workflow with separate
  build/publish jobs, tag/version matching, archive guards, and pinned actions.
- Removed orphaned root LLM modules and their private imports; Git history retains
  them if portfolio archaeology is needed.
- Added bounded SSE streaming, strict/caller-validated JSON, local guardrails,
  content-free events, and versioned portable session snapshots.
- Added approval-required-by-default function tools with sequential protocol
  handling and hard request, round, call, argument, and result budgets.
- Added runnable offline support-triage and approved-support-action proofs plus a
  current competitive boundary assessment.
- Removed 160 tracked `agents/` and `services/` snapshot files so the checkout now
  represents only this standalone product; commit history retains recovery.

## Deferred and blocked work

External release operations:

- Register the `samsarix-agent-engine` distribution and configure protected PyPI
  Trusted Publishing. Verification: an authorized PyPI release installs in an
  empty environment.
- Enable GitHub private vulnerability reporting and verify the documented support
  and conduct mailboxes operationally.

Deliberately deferred local features are the P2 list above; none is required for
the first credible narrow release.

## Known risks

- OpenAI compatibility varies across providers; deterministic tests cover the
  common chat-completions text, SSE, and function-tool shapes, not every compatible
  endpoint variation.
- An application that accepts end-user base URLs can create SSRF risk outside this
  library's operator-trusted configuration model.
- Live state is not durable and can contain prompt/response content until evicted
  or cleared. Exported snapshots are plaintext unless the application encrypts them.
- Tool effects are not transactional or automatically resumable; handlers must be
  idempotent and own recovery, and must minimize results sent back to the provider.
- Agent-level serialization favors ordering over throughput.
- Historical revisions retain legacy application extracts; they are not part of
  the current supported package or checkout.

## Distribution and sustainability

The simplest distribution is a pure-Python wheel plus sdist published through PyPI
Trusted Publishing after owner gates close. No hosted service is needed. A plausible
sustainability model is a maintained core package plus paid integration/support
work; subscriptions, usage billing, and a hosted control plane are out of scope and
unsupported by current evidence.

## Bounded ecosystem research

- The [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
  recommends a `[build-system]` and modern `[project]` metadata; its
  [src-layout guidance](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
  explains how this prevents accidental root imports.
- [Pydantic AI](https://pydantic.dev/docs/ai/core-concepts/agent/) and
  [LangChain](https://docs.langchain.com/oss/python/langchain/agents) provide broad,
  typed tool/workflow agent frameworks. Rebuilding those surfaces is not a credible
  wedge here.
- [LiteLLM](https://docs.litellm.ai/) provides 100+ provider translation, routing,
  fallback, and spend tracking. This repository instead keeps one compatible
  protocol and a custom-provider seam.
- The current comparison and deliberately unbuilt surfaces are recorded in
  [Competitive position](COMPETITIVE_POSITION.md); runnable adoption patterns and
  caller responsibilities are in [Practical use cases](USE_CASES.md).
- Current official GitHub action documentation uses `actions/checkout@v6` and
  `actions/setup-python@v6`; CI pins the current v6 commits and uses read-only
  permissions.

## Historical verification results (2026-08-10)

The competitive expansion was reverified on 2026-08-10 with a fresh, ignored
editable-install environment at `.venv` and an independent wheel-install
environment at `.venv/wheel-smoke`, both on Python 3.11.9.

| Command or check | Actual result |
| --- | --- |
| `python -m pip install -r requirements-test.txt -e .` | Exit 0 in the fresh editable environment; package `0.1.0` and all declared verification tools installed. |
| `python -m ruff format --check src tests examples` | Exit 0; 18 files already formatted. |
| `python -m ruff check src tests examples` | Exit 0; all checks passed. |
| `python -m mypy src tests` | Exit 0; no issues in 12 source/test files under strict mode. |
| `python -m pytest --cov=samsarix_agent_engine --cov-branch --cov-report=term-missing` | Exit 0; 133 passed in 9.84 seconds; 91.62% branch coverage; 90% gate met. |
| `python -m bandit -r src/samsarix_agent_engine -q` | Exit 0; no supported-package findings. |
| `python -m pip_audit -r requirements.txt` | Exit 0; no known runtime dependency vulnerabilities found. |
| `python -m compileall -q src tests examples` | Exit 0. |
| `python -m pip check` | Exit 0 in both fresh environments; no broken requirements. |
| Six scripts under `examples/` | All exited 0, including deterministic structured support triage and an approval-gated ticket mutation. |
| `python -m build` | Exit 0 through isolated builds; produced both wheel and source distribution. |
| `python -m twine check dist/*` | Both artifacts passed. |
| Wheel/sdist archive inspection | Contract passed with 17 wheel entries and 53 sdist entries. Neither artifact contains `agents/`, `services/`, or the old import namespace; both competitive-use-case docs and examples are required by CI/release checks. |
| Fresh wheel installation | Exit 0 with resolved runtime dependencies; package/import versions, public `Agent` and provider imports, `python -m samsarix_agent_engine --help`, and `samsarix-agent --help` all passed. |
| Installed metadata | Wheel reports Samsarix LLC and both working contacts with `License-Expression: MPL-2.0`. |
| Workflow YAML parse | Exit 0; CI jobs are `quality`, `dependency-audit`, and `package`; release jobs are `build` and `publish`. |
| Standalone tree boundary | Exactly 160 tracked legacy files were removed; the physical `agents/` and `services/` directories are absent, with recovery retained at commit `c709e2b`. |

At that checkpoint, GitHub-hosted Python 3.12–3.14 jobs had not run locally.
Subsequent PR #4 and main CI passed the complete hosted 3.11–3.14 matrix.
Live paid-provider calls, PyPI Trusted Publishing, signing, and public upload
remain unrun. Protocol tests use deterministic local HTTP transports.

## Adversarial final review

The final pass re-ran setup, entry points, all examples, bounds,
cancellation/error mapping, package contents, dependency consistency, and
source/document drift checks. The expanded runtime keeps structured parsing,
streaming retention, guardrails, snapshots, approvals, tool arguments/results,
model rounds, calls, and requests under explicit limits. Mutating tools remain
approval-required by default and request budgets are checked before effects.

CI actions remain commit-pinned, both archive formats are guarded, and the artifact
contract now requires the competitive-position documentation and both production
use-case proofs. Historical application extracts were removed instead of being
treated as a security-reviewed deployment surface; any canonical application reuse
requires its own review in the owning repository.

## Release disposition

### Final hardening verification (2026-08-31)

The competitive feature PR [#4](https://github.com/Deathcharge/samsarix-agent-engine/pull/4)
was already merged at `38e8796`. Its
[main CI](https://github.com/Deathcharge/samsarix-agent-engine/actions/runs/31692861551)
passed, including Python 3.11–3.14. The final follow-up closes two remaining
boundary issues and adds a repeatable distribution-installation gate.

Commands below used `.venv/Scripts/python.exe` on Windows (Python 3.11.9);
`python` abbreviates that exact interpreter. No live model credentials were used.

| Command or check | Actual result |
| --- | --- |
| `python -m pip install -e .` | Exit 0; standalone editable installation refreshed successfully. |
| `python -m ruff check src tests examples scripts` | Exit 0; all checks passed. |
| `python -m ruff format --check src tests examples scripts` | Exit 0; 19 files already formatted. |
| `python -m mypy src tests scripts` | Exit 0; strict checking passed for 13 files. |
| `python -m pytest tests/test_models.py tests/test_engine.py tests/test_providers.py -q` | Exit 0; 145 focused tests passed. |
| `python -m pytest --cov=samsarix_agent_engine --cov-branch --cov-report=term-missing` | Exit 0; 160 tests passed; 92.59% combined statement/branch coverage, above the 90% gate. |
| `python -m bandit -r src/samsarix_agent_engine -q` | Exit 0; no findings. |
| `python -m pip_audit -r requirements.txt` | Exit 0; no known runtime dependency vulnerabilities. |
| `python -m pip check` | Exit 0; no broken requirements. |
| `python -m compileall -q src tests examples scripts` | Exit 0. |
| `python -m build --outdir dist/final-20260831` | Exit 0; isolated source distribution and wheel-from-sdist builds passed. |
| `python -m twine check dist/final-20260831/*` | Both distributions passed. |
| `python scripts/smoke_wheel.py dist/final-20260831/samsarix_agent_engine-0.1.0-py3-none-any.whl` | Exit 0; fresh wheel environment, isolated public imports/version, help/version, text/JSON/stdin/streaming CLI, dependency check, and all six examples passed outside the checkout. |
| Workflow YAML and archive guards | Both workflow YAML files parsed; their exact Python archive guard blocks passed locally. Wheel has 17 entries; source distribution has 57. Script, docs, notices, typing marker, and use cases are present; legacy package trees are absent. |
| Installed distribution metadata | Samsarix LLC, both Samsarix contact addresses, and `License-Expression: MPL-2.0` verified. |
| Independent boundary review | Read-only investigation plus one fresh candidate review; 145 focused tests passed independently. No concrete surviving bypass or legitimate regression found. |

Initial new-test runs exposed only test-harness issues: million-character pytest
parameter IDs exceeded Windows environment limits, and a test referenced a
non-exported module attribute under strict mypy. Short IDs and a direct standard
library import resolved both; the final checks above passed.

Security outcomes:

- **Fixed:** secret-bearing exception causes reached ordinary formatted tracebacks
  through sanitized wrappers. Engine callbacks/providers/cleanup, transport and
  response decoding, tool schema parsing, and snapshot parsing now suppress those
  causes. Regression tests inspect complete formatted tracebacks, not just
  exception messages.
- **Fixed:** direct `parse_json_output` calls accepted unbounded raw input before
  JSON decoding. A hard 1,000,000-character ceiling and lower caller-selectable
  `max_chars` reject oversized text before stripping or decoding. Spy tests prove
  the decoder is not called; whitespace, wide arrays, non-ASCII text, exact-limit
  success, and invalid limit configurations were checked.
- Existing cancellation, retryability, public error types, tool-result budget
  errors, failure metrics, successful structured output, and history behavior
  remain covered. The earlier audit-metadata fix remains in main.
- Suppression does not erase exception context/frame locals. Snapshots contain
  conversation text; event identifiers are caller-supplied metadata. The README
  and security policy now state those application responsibilities accurately.

The historical workbench scan targeted `e2160bf`, not current main. Its durable
report assembly encountered artifact-access failures and remains unsealed; it is
not claimed as a completed clean scan. The current code-level fixes, independent
review, executable regression suite, static check, and dependency audit above are
the reproducible acceptance evidence.

CI and the protected release workflow now run the same wheel smoke script before
accepting artifacts. Final follow-up PR checks must pass before merge; post-merge
main CI is checked separately. No PyPI upload, release tag, production deployment,
paid-provider request, mailbox test, or external service provisioning occurred.

### Product disposition

**Competitive alpha release candidate with named external gates.** The bounded
SDK/CLI is independently installable, has two executable business-use-case proofs,
and passes the complete local release journey. The Samsarix identity, MPL-2.0
license, working contact addresses, and standalone repository boundary are explicit.
Public upload remains a no-go until the PyPI project and protected Trusted Publishing
identity are configured and GitHub CI passes the release commit. Version `0.1.0`
remains alpha and unreleased until those gates close.
