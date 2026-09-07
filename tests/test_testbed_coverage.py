"""Unit tests for scripts/testbed_coverage.py."""

import importlib.util
import pathlib
import sys

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_SPEC = importlib.util.spec_from_file_location(
    "testbed_coverage", _SCRIPTS / "testbed_coverage.py"
)
tc = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(tc)

_REUSABLE = "on:\n  workflow_call:\n\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
_PLAIN = "on:\n  push:\n\njobs:\n  a:\n    runs-on: ubuntu-latest\n"


def _workflows(tmp_path, files):
    d = tmp_path / ".github/workflows"
    d.mkdir(parents=True)
    for name, body in files.items():
        (d / name).write_text(body)
    return d


def test_only_a_workflow_call_file_is_judged(tmp_path) -> None:
    """A repository's own PR gate is a caller, not something a consumer can run."""
    d = _workflows(tmp_path, {"pr-checks.yml": _REUSABLE, "ci.yml": _PLAIN})
    assert tc.reusable(d) == ["pr-checks.yml"]


def test_a_workflow_that_says_it_is_not_for_consumers_is_skipped(tmp_path) -> None:
    """The coverage check is itself reusable, and no integration will ever call it.

    Special-casing its filename here would be an exception a reader of the workflow could
    not see, so the workflow declares itself instead.
    """
    d = _workflows(
        tmp_path,
        {
            "testbed-coverage.yml": f"{tc.EXEMPT}\n{_REUSABLE}",
            "pr-checks.yml": _REUSABLE,
        },
    )
    assert tc.uncovered(d, "", "o/r") == ["pr-checks.yml"]


def test_an_uncalled_reusable_workflow_is_reported(tmp_path) -> None:
    """The `ha-panel-ci` case: tagged v1.0.0 with nothing anywhere calling it."""
    d = _workflows(tmp_path, {"panel-bundle.yml": _REUSABLE})
    assert tc.uncovered(d, "", "PineappleEmperor/ha-panel-ci") == ["panel-bundle.yml"]

    caller = (
        "jobs:\n  panel:\n    uses: PineappleEmperor/ha-panel-ci/.github/workflows/"
        "panel-bundle.yml@625d5679d7ca5aca869b10dcbd0b2c759cd0ee26 # v1.0.0\n"
    )
    assert tc.uncovered(d, caller, "PineappleEmperor/ha-panel-ci") == []


def test_a_caller_for_another_repository_does_not_count(tmp_path) -> None:
    """Two CI repositories ship a `release.yml`; only the right owner's call covers it."""
    d = _workflows(tmp_path, {"release.yml": _REUSABLE})
    caller = (
        "jobs:\n  release:\n    uses: PineappleEmperor/ha-integration-ci/.github/"
        "workflows/release.yml@c8b557e9f094cd855c5aecebf2edee8934d23fc4 # v1.0.0\n"
    )
    assert tc.uncovered(d, caller, "PineappleEmperor/release-flow") == ["release.yml"]
    assert tc.uncovered(d, caller, "PineappleEmperor/ha-integration-ci") == []


def test_an_empty_caller_list_is_a_failure_not_a_pass(tmp_path, capsys) -> None:
    """Reading nothing from the testbed must not read as full coverage."""
    _workflows(tmp_path, {"pr-checks.yml": _REUSABLE})

    class _Stdin:
        def read(self) -> str:
            return "\n"

    saved, sys.stdin = sys.stdin, _Stdin()
    try:
        rc = tc.main(
            ["--repo", "o/r", "--workflows", str(tmp_path / ".github/workflows")]
        )
    finally:
        sys.stdin = saved
    assert rc == 1
    assert "NOT CHECKED" in capsys.readouterr().out
