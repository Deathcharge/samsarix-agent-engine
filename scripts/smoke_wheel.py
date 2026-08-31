# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Install a built wheel in a temporary environment and verify offline journeys."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    wheel = Path(sys.argv[1]).resolve(strict=True)
    if wheel.suffix != ".whl":
        raise SystemExit("Expected a built .whl file")
    examples = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.py"))
    if not examples:
        raise SystemExit("Expected offline examples beside the smoke script")
    with tempfile.TemporaryDirectory(prefix="samsarix-wheel-smoke-") as directory:
        root = Path(directory)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        binary = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        cli = binary / ("samsarix-agent.exe" if os.name == "nt" else "samsarix-agent")

        def run(*arguments: str, input_text: str | None = None) -> str:
            result = subprocess.run(  # noqa: S603 - explicit local executables, no shell
                arguments,
                cwd=root,
                input=input_text,
                text=True,
                capture_output=True,
                check=True,
                timeout=180,
            )
            return result.stdout

        run(str(python), "-I", "-m", "pip", "install", str(wheel))
        run(str(python), "-I", "-m", "pip", "check")
        run(
            str(python),
            "-I",
            "-c",
            "import sys; from pathlib import Path; import samsarix_agent_engine as sdk; "
            "from importlib.metadata import version; "
            "assert Path(sdk.__file__).is_relative_to(Path(sys.prefix)); "
            "assert sdk.__version__ == version('samsarix-agent-engine'); "
            "assert sdk.LLMAgentEngine and sdk.Agent and sdk.parse_json_output",
        )
        assert "usage:" in run(str(python), "-I", "-m", "samsarix_agent_engine", "--help")
        assert "samsarix-agent" in run(str(cli), "--version")
        assert "usage:" in run(str(cli), "--help")
        assert run(str(cli), "run", "wheel smoke").strip() == "Echo: wheel smoke"
        assert run(str(cli), "run", input_text="stdin smoke").strip() == "Echo: stdin smoke"
        assert (
            json.loads(run(str(cli), "run", "json smoke", "--json"))["content"]
            == "Echo: json smoke"
        )
        assert run(str(cli), "run", "stream smoke", "--stream").strip() == "Echo: stream smoke"
        for example in examples:
            run(str(python), "-I", str(example))
        print(f"Wheel install, imports, CLI modes, pip check, and {len(examples)} examples passed.")


if __name__ == "__main__":
    main()
