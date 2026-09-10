"""Unit tests for scripts/release_notes.py.

Load the standalone script by path; it is not an importable package.
"""

import importlib.util
import pathlib
import sys

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_SPEC = importlib.util.spec_from_file_location(
    "release_notes", _SCRIPTS / "release_notes.py"
)
rn = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(rn)


def test_groups_by_commit_type_not_pr_label(monkeypatch) -> None:
    """A fix inside a feature PR lands under Fixes."""
    log = "aaa\x00feat: add polling\nbbb\x00fix: close the session\nccc\x00chore: tidy"
    monkeypatch.setattr(rn, "_git", lambda *a: log)
    monkeypatch.setattr(rn, "pr_for", lambda sha, head: "7")
    out = rn.build("v1..HEAD", repo_url="https://x/y", head="HEAD")

    assert (
        out.index("## 🚀 Features")
        < out.index("## 🔧 Fixes")
        < out.index("## 🧰 Maintenance")
    )
    fixes = out.split("## 🔧 Fixes")[1].split("##")[0]
    assert "close the session" in fixes
    assert "add polling" not in fixes


def test_merge_commits_and_version_bumps_are_dropped(monkeypatch) -> None:
    """Neither is a changelog entry."""
    log = (
        "aaa\x00Merge pull request #3 from o/b\n"
        "bbb\x00chore: bump manifest version to v1.2.3\n"
        "ccc\x00fix: a real change"
    )
    monkeypatch.setattr(rn, "_git", lambda *a: log)
    monkeypatch.setattr(rn, "pr_for", lambda sha, head: None)
    out = rn.build("v1..HEAD")
    assert "a real change" in out
    assert "Merge pull request" not in out
    assert "bump manifest version" not in out


def test_compare_link_appended(monkeypatch) -> None:
    """Every surveyed HACS repo ends with a full-changelog compare link."""
    monkeypatch.setattr(rn, "_git", lambda *a: "aaa\x00feat: thing")
    monkeypatch.setattr(rn, "pr_for", lambda sha, head: None)
    out = rn.build(
        "v1..HEAD", repo_url="https://x/y", previous="v1.0.0", version="1.1.0"
    )
    assert (
        "**Full Changelog**: [v1.0.0...v1.1.0](https://x/y/compare/v1.0.0...v1.1.0)"
        in out
    )


def test_no_changes_says_so(monkeypatch) -> None:
    """An empty range must not render an empty document."""
    monkeypatch.setattr(rn, "_git", lambda *a: "")
    assert rn.build("v1..HEAD").strip() == rn.EMPTY_RANGE


def test_headings_and_order_come_from_the_shared_vocabulary(monkeypatch) -> None:
    """One table in commit_summary.py names every heading; the breaking one is plural."""
    assert rn.ORDER is rn.cs.ORDER
    expected = {k: f"## {v}" for k, v in rn.cs.HEADINGS.items()}
    assert expected == rn.HEADINGS
    assert rn.cs.HEADINGS["breaking"] == "🚨 Breaking Changes"
    log = "aaa\x00feat!: drop it"
    monkeypatch.setattr(rn, "_git", lambda *a: log)
    monkeypatch.setattr(rn, "pr_for", lambda sha, head: None)
    assert rn.build("v1..HEAD").startswith("## 🚨 Breaking Changes")


def _crn():
    """The notes checker, loaded from scripts/ like the other single-file tools."""
    spec = importlib.util.spec_from_file_location(
        "check_release_notes", _SCRIPTS / "check_release_notes.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_empty_range_sentinel_is_flagged() -> None:
    """A body that is only the empty-range sentinel."""
    crn = _crn()
    assert crn.EMPTY_RANGE is rn.EMPTY_RANGE
    assert any("empty-range sentinel" in p for p in crn.check(rn.EMPTY_RANGE))
    assert not any(
        "empty-range sentinel" in p for p in crn.check("## 🔧 Fixes\n\n- a real change")
    )


def test_draft_placeholder_is_flagged(tmp_path) -> None:
    """A body that is the drafter config's `template`, or empty."""
    crn = _crn()
    cfg = tmp_path / "release-drafter.yml"
    cfg.write_text("template: |\n  _Release notes were not generated._\n")
    placeholder = crn.placeholder_from(cfg)
    assert placeholder == "_Release notes were not generated._"
    assert any(
        "draft placeholder" in p
        for p in crn.check(
            "_Release notes were not generated._\n", placeholder=placeholder
        )
    )
    assert any("draft placeholder" in p for p in crn.check("   \n"))
    assert not any("draft placeholder" in p for p in crn.check("## 🔧 Fixes\n\n- x"))


def test_a_missing_config_leaves_only_the_empty_body_check(tmp_path) -> None:
    """No drafter config beside the checkout."""
    crn = _crn()
    assert crn.placeholder_from(tmp_path / "absent.yml") is None
    assert not any("draft placeholder" in p for p in crn.check("pending"))


def test_a_major_with_no_breaking_section_is_flagged() -> None:
    """`v2.0.0` after an earlier release, notes with only Features."""
    crn = _crn()
    notes = "## 🚀 Features\n\n- add a thing\n"
    assert any("Breaking Changes" in p for p in crn.check(notes, "2.0.0"))
    assert not any(
        "Breaking Changes" in p
        for p in crn.check("## 🚨 Breaking Changes\n\n- drop it\n", "2.0.0")
    )


def test_a_first_release_is_not_held_to_the_major_rule() -> None:
    """`v1.0.0` with no previous release: nothing to have broken from."""
    crn = _crn()
    notes = "## 🚀 Features\n\n- add a thing\n"
    assert not any(
        "Breaking Changes" in p for p in crn.check(notes, "1.0.0", first_release=True)
    )
    assert any("Breaking Changes" in p for p in crn.check(notes, "1.0.0"))


def test_drafter_body_means_the_generator_never_ran() -> None:
    """A body still in release-drafter's PR-per-line shape."""
    crn = _crn()
    drafter = "## Fixes\n\n- fix: close the session @dev (#12)\n"
    assert any("release-drafter" in p for p in crn.check(drafter))
    assert not any(
        "release-drafter" in p
        for p in crn.check("## 🔧 Fixes\n\n- close the session ([#12](u))\n")
    )


GH_NOTES = (
    "## What's Changed\n"
    "* fix: close the session by @someone in https://x/y/pull/7\n"
    "\n"
    "## New Contributors\n"
    "* @newbie made their first contribution in https://x/y/pull/7\n"
    "* @dependabot[bot] made their first contribution in https://x/y/pull/8\n"
    "\n"
    "**Full Changelog**: https://x/y/compare/v1.0.0...v1.1.0"
)


def test_new_contributors_takes_only_that_section() -> None:
    """GitHub's `What's Changed` and compare line must not come with it."""
    block = rn.new_contributors(GH_NOTES)
    assert block.startswith("## New Contributors")
    assert "@newbie" in block
    assert "What's Changed" not in block
    assert "Full Changelog" not in block


def test_new_contributors_drops_bots() -> None:
    """Thanking dependabot for its first contribution is noise, not credit."""
    assert "dependabot" not in rn.new_contributors(GH_NOTES)
    assert "dependabot" in rn.new_contributors(GH_NOTES, include_bots=True)


def test_new_contributors_empty_when_only_bots() -> None:
    """Filtering can empty the section, and a bare heading is worse than none."""
    notes = (
        "## New Contributors\n"
        "* @dependabot[bot] made their first contribution in https://x/y/pull/8"
    )
    assert rn.new_contributors(notes) == ""


def test_new_contributors_spliced_before_the_compare_link(monkeypatch) -> None:
    """The block belongs in the body, above the compare link this file writes."""
    monkeypatch.setattr(rn, "_git", lambda *a: "aaa\x00feat: thing")
    monkeypatch.setattr(rn, "pr_for", lambda sha, head: None)
    out = rn.build(
        "v1..HEAD",
        repo_url="https://x/y",
        previous="v1.0.0",
        version="1.1.0",
        github_notes=GH_NOTES,
    )
    assert out.index("## New Contributors") < out.index("**Full Changelog**")
    assert out.count("**Full Changelog**") == 1
