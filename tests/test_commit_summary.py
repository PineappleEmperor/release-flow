"""Unit tests for scripts/commit_summary.py.

Load the standalone script by path — it is not an importable package.
"""

import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "commit_summary",
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "commit_summary.py",
)
cs = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(cs)


# --- classify ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "group", "desc"),
    [
        ("feat: add reconfigure flow", "feat", "add reconfigure flow"),
        ("feature: add thing", "feat", "add thing"),
        ("fix: close the session", "fix", "close the session"),
        ("chore: tidy", "maint", "tidy"),
        ("docs: explain", "maint", "explain"),
        ("refactor: split api.py", "maint", "split api.py"),
        ("perf: cache lookups", "maint", "cache lookups"),
        ("test: cover unload", "maint", "cover unload"),
        ("build: pin ruff", "maint", "pin ruff"),
        ("ci: add pytest step", "maint", "add pytest step"),
        ("style: reformat", "maint", "reformat"),
        # Breaking wins over the base type, with or without a scope.
        ("feat!: drop create-dev-pr", "breaking", "drop create-dev-pr"),
        ("fix!: change the payload shape", "breaking", "change the payload shape"),
        ("chore(deps)!: require python 3.14", "breaking", "require python 3.14"),
        ("feat(coordinator): add polling", "feat", "add polling"),
        ("revert: undo the flow change", "other", "undo the flow change"),
        # Case-insensitive type.
        ("FEAT: shout", "feat", "shout"),
        ("Fix: capitalised", "fix", "capitalised"),
        # No space after the colon.
        ("feat:no space", "feat", "no space"),
        # Extra whitespace is trimmed.
        ("fix:   padded   ", "fix", "padded"),
        # Not Conventional Commits at all.
        ("Merge branch 'main' into feat/x", "other", "Merge branch 'main' into feat/x"),
        ("WIP", "other", "WIP"),
        ("", "other", ""),
        # A scope containing a colon still parses (the group is [^)]*).
        ("feat(a:b): scoped", "feat", "scoped"),
        # Empty description keeps the raw subject rather than rendering "- ".
        ("feat:", "other", "feat:"),
        ("chore: ", "other", "chore:"),
    ],
)
def test_classify(subject: str, group: str, desc: str) -> None:
    """Each subject lands in the expected group with a clean description."""
    assert cs.classify(subject) == (group, desc)


# --- the version-bump filter (the regression that shipped) ------------------


@pytest.mark.parametrize(
    "subject",
    [
        "chore: bump manifest version to v5.0.1",
        "chore: bump plugin version to 5.0.1",
        "chore: bump version to 5.0.1",
        "chore: bump the manifest version",
        "chore: bump integration version to 1.2.3",
        # The bare form the release workflow actually writes. It leaked into
        # Maintenance in the v7.0.1 draft because the pattern demanded the word
        # "version" after the noun.
        "chore: bump to 7.0.1",
        "chore: bump the ha plugin to 6.4.0",
    ],
)
def test_release_plumbing_is_dropped(subject: str) -> None:
    """The manifest/plugin bump is plumbing, not a changelog entry."""
    assert cs.group([subject, "fix: real change"])["maint"] == []


@pytest.mark.parametrize(
    "subject",
    [
        "chore: bump actions/checkout from 6 to 7",
        "chore: bump actions/checkout from 6.0.0 to 7.0.1",
        "chore: bump pytest-homeassistant-custom-component from 0.13.350 to 0.13.354",
        "chore: bump homeassistant floor to 2026.8.0",
        "chore(deps): bump aiohttp from 3.9.0 to 3.10.1",
    ],
)
def test_dependency_bumps_survive(subject: str) -> None:
    """Dependabot's bumps are real changes and must reach the notes."""
    assert cs.group([subject])["maint"] == [subject.split(": ", 1)[1]]


# --- winning (drives the title suggestion) ----------------------------------


@pytest.mark.parametrize(
    ("subjects", "expected"),
    [
        (["feat: a"], "feat"),
        (["fix: a"], "fix"),
        (["chore: a"], "maint"),
        # Highest impact wins regardless of order.
        (["fix: a", "feat: b"], "feat"),
        (["feat: b", "fix: a"], "feat"),
        (["chore: a", "fix: b"], "fix"),
        (["fix: b", "chore: a"], "fix"),
        (["chore: a", "feat!: b", "fix: c"], "breaking"),
        (["feat: a", "feat!: b"], "breaking"),
        # No commits at all -> the most conservative suggestion.
        ([], "maint"),
        (["chore: bump manifest version to v1.0.0"], "maint"),
        # A lone unmappable subject.
        (["revert: undo"], "other"),
    ],
)
def test_winning(subjects: list[str], expected: str) -> None:
    """The suggested title type reflects the most impactful commit present."""
    assert cs.winning(subjects) == expected


def test_every_group_has_a_title_suggestion() -> None:
    """No group can be reached that lacks a suggestion for title-check."""
    for key in cs.ORDER:
        assert key in cs.SUGGESTIONS


def test_title_uses_the_winning_commit_s_own_type() -> None:
    """The title carries the type and text of the winning commit, not its category."""
    assert cs.title_for(["docs: describe the ci"]) == "docs: describe the ci"
    assert cs.title_for(["feat: add a thing", "fix: correct it"]) == "feat: add a thing"
    assert (
        cs.title_for(["feat!: drop python 3.13", "docs: note it"])
        == "feat!: drop python 3.13"
    )
    assert cs.title_for(["refactor: tidy internals"]) == "refactor: tidy internals"
    assert cs.title_for(["perf: cache it", "ci: pin it"]) == "perf: cache it"
    assert cs.title_for(["fix: one", "chore: bump to 7.3.0"]) == "fix: one"


def test_a_type_outside_the_allowlist_is_retyped_chore() -> None:
    """`revert:` is a valid commit type that no PR title may carry."""
    assert (
        cs.title_for(["revert: undo the flow change"]) == "chore: undo the flow change"
    )


def test_the_allowlist_is_the_ten_types() -> None:
    """The types a title may carry are the two that label and the eight that fold."""
    expected = {"feat", "fix"} | set(cs.MAINT)
    assert set(cs.LABELLABLE) == expected


def test_the_label_a_prs_commits_entitle_it_to() -> None:
    """A `fix:` title over a `feat!:` commit: the commits, not the title, decide."""
    assert cs.label_for(["feat!: drop python 3.13", "fix: tidy"]) == "xfeat"
    assert cs.label_for(["feat: add a thing", "fix: correct it"]) == "feature"
    assert cs.label_for(["fix: correct it"]) == "fix"
    assert cs.label_for(["refactor: tidy internals"]) == "chore"
    assert cs.label_for(["docs: describe the ci"]) == "chore"
    # No commits at all still resolves, rather than raising in the middle of a PR check.
    assert cs.label_for([]) == "chore"


def test_every_group_maps_to_a_managed_label() -> None:
    """A group with no label would make the correctness check unresolvable."""
    for key in cs.ORDER:
        assert cs.LABEL_FOR[key] in cs.MANAGED_LABELS
