# Release checklist

Publishing is intentionally blocked by the `Private :: Do Not Upload` classifier
until all owner gates below are closed. Do not remove that classifier as a routine
engineering cleanup.

## Owner gates

1. Confirm that `helix-llm-agent-engine` is the intended distribution name and
   namespace. PyPI returned no project for that name on 2026-07-28, but availability
   must be checked again immediately before registration.
2. Replace or formally approve the repository license files. The current root
   license names `Helix Licensing System`, contains timing terms that appear
   internally inconsistent, and conflicts with `LICENSE.PROPRIETARY`.
3. Confirm the legal licensor name, security contact, support contact, and project
   URLs. Do not infer them from stale repository text.
4. Create or select the PyPI project and configure a GitHub environment named
   `pypi` with required reviewers.
5. Configure PyPI Trusted Publishing for the exact GitHub repository, workflow,
   environment, and release tag pattern. Do not add a long-lived PyPI token.

## Local release candidate verification

From a fresh virtual environment:

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src/helix_llm_agent_engine
python -m bandit -r src/helix_llm_agent_engine -q
python -m pip_audit -r requirements.txt
python -m pytest --cov=helix_llm_agent_engine --cov-report=term-missing
python -m build
python -m twine check dist/*
```

Install the built wheel into a second empty environment and run:

```bash
helix-agent --version
helix-agent run "release smoke test"
python -c "from helix_llm_agent_engine import LLMAgentEngine"
```

Inspect both wheel and sdist contents. They must include only the supported package,
documentation, and license files; `agents/` and `services/` must be absent.

## Authorized publication sequence

After the owner gates are documented and the upload-blocking classifier is removed
in review:

1. Update `CHANGELOG.md`, version metadata, and the release tag together.
2. Run the local and CI acceptance suite.
3. Create a signed/tagged GitHub release from the reviewed commit.
4. Let the environment-protected Trusted Publishing workflow build from the tag
   and publish; never upload a local dirty-worktree artifact.
5. Install from PyPI into an empty environment and repeat the two CLI smoke tests.
6. If verification fails, yank the release and document the reason; versions cannot
   be overwritten on PyPI.
