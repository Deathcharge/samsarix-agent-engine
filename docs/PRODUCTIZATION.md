# Productization record

Last updated: 2026-08-08

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
- Include only `samsarix_agent_engine*` in distributions. Preserve but explicitly
  exclude the legacy backend snapshot.
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
- [ ] Remove or relocate the preserved legacy snapshot after owner portfolio review.

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
- [x] Complete final security artifacts and adversarial review.

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
- Legacy source remains visible and may be mistaken for supported code if readers
  ignore the package and boundary documentation.

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

## Final verification results

Verification used a fresh editable-install environment at
`%TEMP%\samsarix-agent-engine-verify-7c33c82de6b94286be602e9843e6aff4\edit2`
and a second fresh wheel-install environment under the same root on Python 3.11.9.

| Command or check | Actual result |
| --- | --- |
| `python -m pip install -e ".[dev]"` | Exit 0 in the first fresh environment; package `0.1.0` and declared tools installed. |
| `python -m ruff format --check src tests examples` | Exit 0; 15 files already formatted. |
| `python -m ruff check src tests examples` | Exit 0; all checks passed. |
| `python -m mypy src/samsarix_agent_engine` | Exit 0; no issues in 7 source files under strict mode. |
| `python -m pytest --cov=samsarix_agent_engine --cov-report=term-missing` | Exit 0; 54 passed; 91.41% branch coverage; 90% gate met. |
| `python -m bandit -r src/samsarix_agent_engine -q` | Exit 0; no supported-package findings. |
| `python -m pip_audit -r requirements.txt` | Exit 0; no known runtime dependency vulnerabilities found. |
| `python -m compileall -q src tests examples` | Exit 0. |
| `python -m pip check` | Exit 0 in both fresh environments; no broken requirements. |
| Four scripts under `examples/` | All exited 0 with the documented echo, custom-provider, collaboration, and reset/error behavior. |
| Module and `samsarix-agent` entry points | `--version`, offline JSON, stdin, and text paths exited 0; the earlier unreachable-endpoint check returned sanitized exit code 3. |
| `python -m build --sdist` and `python -m build --wheel` | Exit 0 using the declared isolated build requirement; built both distributions. |
| `python -m twine check dist/*` | Both artifacts passed. |
| Wheel/sdist archive inspection | Neither contains `agents/`, `services/`, or the old import namespace; the wheel contains 7 modules, `py.typed`, metadata, and 4 licensing/notice files. The sdist also contains policies, docs, examples, and citation metadata. |
| Fresh wheel installation | Exit 0; import, renamed base exception, module/CLI version, text/JSON invocation, `py.typed`, licensing files, and `pip check` all passed outside the repository. |
| Citation and license metadata | `CITATION.cff` parsed as YAML; wheel metadata reports Samsarix LLC contacts and `License-Expression: MPL-2.0`; the license SHA-256 matches the portfolio's unmodified MPL-2.0 copy. |
| Workflow YAML parse | Exit 0; CI jobs are `quality`, `dependency-audit`, and `package`; release jobs are `build` and `publish`. |
| `git diff --check` | Exit 0. |
| Prior full security contract | The contract bound to `dddf4f4` remains valid with 0 supported-surface findings; this branding/package diff separately passed strict tests, Bandit, dependency audit, archive inspection, and manual diff review. |

The exploratory `python -m build --no-isolation` failed because the first virtual
environment's preinstalled `setuptools` was older than the declared
`setuptools>=77` build requirement. This is not the documented release path;
normal isolated `python -m build` installed the declared backend and passed.

Not run locally: GitHub-hosted Actions, Python 3.12–3.14 matrix jobs, a live paid
provider call, PyPI Trusted Publishing, signing, or a public upload. Those require
external runners, credentials, owner authorization, or closure of publishing gates.
All protocol tests use deterministic local HTTP transports.

## Adversarial final review

The final pass re-ran setup, entry points, examples, bounds, cancellation/error
mapping, package contents, dependency consistency, secret-pattern filename scans,
and source/document drift checks. It found and fixed three issues before acceptance:
unbounded custom-provider output retention, unsanitized provider request IDs/text
terminal controls, and a CLI stdin-limit path that could escape clean error mapping.
Provider replacement cleanup is now retained, idempotent, exhaustive, and sanitized;
CI actions are commit-pinned and both archive formats are guarded. The branding pass
also caught and fixed two release-metadata defects before acceptance: setuptools
rejects `mailto:` project URLs, and PEP 639 license expressions cannot be combined
with the superseded license classifier.

The security scan statically inventoried retained legacy code and manually assessed
its Python execution, subprocess, path, and weak-digest candidates. None is reachable
from the distributed product. This is not a deployment-safety finding for those
extracts: they remain explicitly unsupported and require a new scan in their
canonical application before reuse.

## Release disposition

**Release candidate with named external gates.** The narrow SDK/CLI is independently
installable and its release-candidate journey passes locally with no actionable P0
or supported-surface P1 remaining. The Samsarix identity, MPL-2.0 license, and
working contact addresses are documented. Public upload is a no-go until repository
naming is finalized, the PyPI project and protected Trusted Publishing identity are
configured, and GitHub CI passes on the release commit. Version `0.1.0` remains
alpha and unreleased until those gates close.
