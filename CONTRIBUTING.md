# Contributing

Contributions should keep the supported product small, independently installable,
and free of runtime dependencies on private Samsarix repositories.

## Setup

```bash
git clone https://github.com/Deathcharge/helix-hub-shared.git
cd helix-hub-shared
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Required checks

```bash
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src/samsarix_agent_engine
python -m bandit -r src/samsarix_agent_engine -q
python -m pip_audit -r requirements.txt
python -m pytest --cov=samsarix_agent_engine --cov-report=term-missing
python -m build
python -m twine check dist/*
```

Add tests that exercise implementation, not mocks of the object under test. Network
tests must use deterministic local transports or fixtures and must not require paid
credentials.

## Scope

- `src/samsarix_agent_engine/` is the supported product.
- `tests/` and `examples/` must match the installed public API.
- `agents/` and `services/` are legacy extracts. Do not expand or restore their
  private-repository coupling. Changes there need a separately justified owner
  decision and must not enter the distribution accidentally.
- Do not add a provider SDK to the required dependency set when a custom provider
  adapter can keep it optional.
- Do not add telemetry, hosted infrastructure, billing, or persistence without a
  concrete product requirement and privacy/security design.

## Pull requests

Keep changes focused, update user documentation and `CHANGELOG.md` for observable
behavior, state any compatibility impact, and include exact verification commands.
Use conventional commit prefixes such as `feat:`, `fix:`, `docs:`, and `test:` when
helpful; no specific commit-message format is enforced by tooling.

Follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report vulnerabilities using
[SECURITY.md](SECURITY.md), not a public issue containing exploit details.

Unless stated otherwise before acceptance, contributions are submitted under
MPL-2.0, the project's license. Contributors retain copyright in their work; see
[LICENSING.md](LICENSING.md) for the ownership and contribution model.
