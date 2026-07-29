# Release checklist

The source, package metadata, repository identity, and contacts are aligned, but
public upload is still gated on protected publishing identity and CI.

## Owner gates

1. The GitHub repository was renamed to `samsarix-agent-engine` on 2026-07-29.
   Configure publisher identity against that exact owner/repository so project
   URLs and trusted-publisher claims stay aligned.
2. Recheck and register the `samsarix-agent-engine` PyPI distribution. PyPI returned
   404 for that name on 2026-07-28, but a 404 is not a reservation.
3. Create a GitHub environment named
   `pypi` with required reviewers.
4. Configure PyPI Trusted Publishing for the exact GitHub owner/repository,
   `.github/workflows/release.yml`, and `pypi` environment. Do not add a long-lived
   PyPI token.
5. Enable private vulnerability reporting/GitHub Security Advisories and verify
   delivery to support@samsarix.com.

## Local release candidate verification

From a fresh virtual environment:

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src/samsarix_agent_engine
python -m bandit -r src/samsarix_agent_engine -q
python -m pip_audit -r requirements.txt
python -m pytest --cov=samsarix_agent_engine --cov-report=term-missing
python -m build
python -m twine check dist/*
```

Install the built wheel into a second empty environment and run:

```bash
samsarix-agent --version
samsarix-agent run "release smoke test"
python -c "from samsarix_agent_engine import LLMAgentEngine"
```

Inspect both wheel and sdist contents. They must include only the supported package,
documentation, and license files; `agents/` and `services/` must be absent.

## Authorized publication sequence

After the owner gates are documented:

1. Update `CHANGELOG.md`, version metadata, and the release tag together.
2. Run the local and CI acceptance suite.
3. Create tag `v<version>` on the reviewed commit and publish its GitHub release;
   the workflow rejects any tag that does not match package metadata.
4. Let the environment-protected Trusted Publishing workflow build from the tag
   and publish; never upload a local dirty-worktree artifact.
5. Install from PyPI into an empty environment and repeat the two CLI smoke tests.
6. If verification fails, yank the release and document the reason; versions cannot
   be overwritten on PyPI.
