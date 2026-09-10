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
    """The coverage check is itself reusable, and no integration will ever call it."""
    d = _workflows(
        tmp_path,
        {
            "testbed-coverage.yml": f"{tc.EXEMPT}\n{_REUSABLE}",
            "pr-checks.yml": _REUSABLE,
        },
    )
    assert tc.uncovered(d, "", "o/r") == ["pr-checks.yml"]


def test_an_uncalled_reusable_workflow_is_reported(tmp_path) -> None:
    """The case the check exists for, and then the same workflow once a caller names it."""
    d = _workflows(tmp_path, {"panel-bundle.yml": _REUSABLE})
    assert tc.uncovered(d, "", "PineappleEmperor/ha-panel-ci") == ["panel-bundle.yml"]

    caller = (
        "jobs:\n  panel:\n    uses: PineappleEmperor/ha-panel-ci/.github/workflows/"
        "panel-bundle.yml@625d5679d7ca5aca869b10dcbd0b2c759cd0ee26 # v1.0.0\n"
    )
    assert tc.uncovered(d, caller, "PineappleEmperor/ha-panel-ci") == []


def test_a_quoted_uses_value_still_counts(tmp_path) -> None:
    """YAML lets a caller quote it, and a false "never called" is the worst verdict here."""
    d = _workflows(tmp_path, {"pr-checks.yml": _REUSABLE})
    for quote in ('"', "'"):
        caller = f"jobs:\n  pr:\n    uses: {quote}o/r/.github/workflows/pr-checks.yml@abc{quote}\n"
        assert tc.uncovered(d, caller, "o/r") == []


def test_a_caller_inside_a_comment_does_not_count(tmp_path) -> None:
    """A commented-out caller has never run, so counting it is the failure inverted."""
    d = _workflows(tmp_path, {"pr-checks.yml": _REUSABLE})
    caller = "jobs:\n  # uses: o/r/.github/workflows/pr-checks.yml@abc\n"
    assert tc.uncovered(d, caller, "o/r") == ["pr-checks.yml"]

    # The version comment that follows every real pin must survive the same stripping.
    live = "jobs:\n  pr:\n    uses: o/r/.github/workflows/pr-checks.yml@abc # v1.0.0\n"
    assert tc.uncovered(d, live, "o/r") == []


def test_a_list_form_trigger_is_still_a_reusable_workflow(tmp_path) -> None:
    """`on: [workflow_call]` is valid YAML and was silently dropped, so never judged."""
    d = _workflows(
        tmp_path,
        {
            "list.yml": "on: [workflow_call]\njobs:\n  a:\n    runs-on: ubuntu-latest\n",
            "bare.yml": "on: workflow_call\njobs:\n  a:\n    runs-on: ubuntu-latest\n",
        },
    )
    assert tc.reusable(d) == ["bare.yml", "list.yml"]


def test_a_workflow_that_is_not_a_mapping_is_skipped(tmp_path) -> None:
    """A file parsing to a scalar crashed the run, so nothing at all was judged."""
    d = _workflows(
        tmp_path, {"junk.yml": "just a string\n", "pr-checks.yml": _REUSABLE}
    )
    assert tc.reusable(d) == ["pr-checks.yml"]


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
