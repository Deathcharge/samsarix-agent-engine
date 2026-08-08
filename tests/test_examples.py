from __future__ import annotations

import runpy
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("example", "expected_lines"),
    [
        (
            "support_triage.py",
            {
                "route=billing priority=2 summary=Duplicate charge",
                "events=request.started,request.succeeded,session.exported",
                "snapshot_chars=293",
            },
        ),
        (
            "approved_support_action.py",
            {
                "Ticket T-42 is now closed.",
                "stored_status=closed",
                (
                    "events=request.started,tool.requested,tool.approved,tool.succeeded,"
                    "request.succeeded,request.started,request.succeeded"
                ),
            },
        ),
    ],
)
def test_offline_use_case_example(
    example: str,
    expected_lines: set[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(str(_ROOT / "examples" / example), run_name="__main__")
    assert set(capsys.readouterr().out.splitlines()) == expected_lines
