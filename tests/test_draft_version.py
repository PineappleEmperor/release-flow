"""Unit tests for scripts/draft_version.py."""

import importlib.util
import json
import pathlib
import sys

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_SPEC = importlib.util.spec_from_file_location(
    "draft_version", _SCRIPTS / "draft_version.py"
)
dv = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(dv)


def test_a_prerelease_as_the_newest_release_pins_its_base() -> None:
    """Newest published release `v1.0.0rc1`."""
    releases = [{"tagName": "v1.0.0rc1", "isPrerelease": True}]
    assert dv.pinned_version(releases) == "1.0.0"


def test_a_final_anywhere_in_the_history_pins_nothing() -> None:
    """Newest published release `v1.0.0`, with an older rc behind it."""
    releases = [
        {"tagName": "v1.0.0", "isPrerelease": False},
        {"tagName": "v1.0.0rc1", "isPrerelease": True},
    ]
    assert dv.pinned_version(releases) == ""


def test_no_published_release_pins_nothing() -> None:
    """An empty list, as a repository with only drafts returns."""
    assert dv.pinned_version([]) == ""


def test_an_rc_line_after_a_final_pins_nothing() -> None:
    """`v2.0.0rc3` newest, `v1.4.0` behind it.

    The pin exists for a repository release-drafter cannot resolve at all. Once one full
    release exists it resolves from that release and the labels since it, and an override
    can only contradict them — it once would have shipped two breaking changes as
    `v7.2.1` because an rc for `7.2.1` was open.
    """
    releases = [
        {"tagName": "v2.0.0rc3", "isPrerelease": True},
        {"tagName": "v1.4.0", "isPrerelease": False},
    ]
    assert dv.pinned_version(releases) == ""


def test_newest_means_most_recently_published_not_first_listed() -> None:
    """Among candidates only, the base comes from the one published last, not listed first.

    An rc and its final draft are created in the same run, so creation order says nothing
    about which came out first.
    """

    def rel(tag: str, pre: bool, at: str) -> dict:
        return {"tagName": tag, "isPrerelease": pre, "publishedAt": at}

    releases = [
        rel("v0.4.0rc1", True, "2026-09-06T08:05:00Z"),
        rel("v0.3.0rc2", True, "2026-09-06T08:40:00Z"),
        rel("v0.3.0rc1", True, "2026-09-04T19:26:38Z"),
    ]
    assert dv.pinned_version(releases) == "0.3.0"


def test_base_of_a_version() -> None:
    """`--base` strips any prerelease suffix and the `v`."""
    assert dv.base("v1.0.0rc2") == "1.0.0"
    assert dv.base("0.3.1beta1") == "0.3.1"
    assert dv.base("1.2.3") == "1.2.3"


def test_main_reads_the_release_list_from_stdin(capsys, monkeypatch) -> None:
    """The workflow pipes `gh release list --json tagName,isPrerelease` in."""
    monkeypatch.setattr(
        "sys.stdin",
        _Stdin(json.dumps([{"tagName": "v0.1.0rc4", "isPrerelease": True}])),
    )
    assert dv.main([]) == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_main_base_mode(capsys) -> None:
    """`--base v7.0.0rc1` prints `7.0.0`."""
    assert dv.main(["--base", "v7.0.0rc1"]) == 0
    assert capsys.readouterr().out.strip() == "7.0.0"


def _draft(tag: str) -> dict:
    return {"tagName": tag, "isDraft": True}


def test_a_push_removes_the_candidate_of_a_base_the_draft_moved_past() -> None:
    """The testbed on 2026-09-10: `v0.3.1` renamed to `v0.4.0`, `v0.3.1rc1` left behind."""
    releases = [
        _draft("v0.4.0"),
        _draft("v0.4.0rc1"),
        _draft("v0.3.1rc1"),
        {"tagName": "v0.3.0", "isDraft": False},
    ]
    assert dv.stale_drafts(releases, drafting="0.4.0") == ["v0.3.1rc1"]


def test_a_push_keeps_the_drafts_of_its_own_base_and_every_published_release() -> None:
    """A published candidate of an older base is history, never a draft to remove."""
    releases = [
        _draft("v1.1.0"),
        _draft("v1.1.0rc1"),
        {"tagName": "v1.0.2rc1", "isDraft": False},
    ]
    assert dv.stale_drafts(releases, drafting="1.1.0") == []


def test_a_push_keeps_the_drafts_of_a_higher_base() -> None:
    """Only a base the draft has moved past is orphaned; one above it is not."""
    releases = [_draft("v0.4.0"), _draft("v0.4.0rc2"), _draft("v0.3.0rc3")]
    assert dv.stale_drafts(releases, drafting="0.3.0") == []


def test_a_push_on_a_pinned_version_removes_nothing() -> None:
    """With no full release, the pin follows whichever candidate was published last.

    Publishing `v0.3.0rc2` and then `v0.4.0rc1` pins `0.4.0`, and the other order pins
    `0.3.0`, so which line's drafts survived would depend on that order. A pinned push
    leaves every draft for the first final's publish to clear.
    """
    releases = [_draft("v0.3.0"), _draft("v0.3.0rc3"), _draft("v0.4.0rc2")]
    assert dv.stale_drafts(releases, drafting="0.4.0", pinned=True) == []


def test_publishing_a_final_removes_every_draft_at_or_below_its_base() -> None:
    """release-flow on 2026-09-10: `v1.1.0` published with `v1.0.2rc1` still a draft."""
    releases = [_draft("v1.0.2rc1"), _draft("v1.1.0rc1"), _draft("v1.2.0rc1")]
    assert dv.stale_drafts(releases, published="v1.1.0") == ["v1.0.2rc1", "v1.1.0rc1"]


def test_publishing_matches_the_version_not_a_prefix_of_its_tag() -> None:
    """A tag prefix matches `v1.1.10rc1` when publishing `v1.1.1`; a version does not."""
    releases = [_draft("v1.1.10rc1"), _draft("v1.1.1rc1")]
    assert dv.stale_drafts(releases, published="v1.1.1") == ["v1.1.1rc1"]


def test_publishing_anything_but_an_exact_base_removes_nothing() -> None:
    """Final is `X.Y.Z` after one leading `v`, as the workflow tests `V` against its base."""
    releases = [_draft("v1.1.0"), _draft("v1.1.0rc3"), _draft("v1.0.2rc1")]
    for tag in (
        "v1.1.0rc2",
        "v1.1.0b1",
        "v1.1.0beta1",
        "v1.1.0dev1",
        "v1.1.0.post1",
        "v1.1.0-rc.1",
        "vv1.1.0",
    ):
        assert dv.stale_drafts(releases, published=tag) == [], tag


def test_one_leading_v_is_optional_in_a_published_final() -> None:
    """The workflow strips one `v` from the tag, so `1.1.0` is as final as `v1.1.0`."""
    releases = [_draft("v1.1.0rc3"), _draft("v1.2.0rc1")]
    assert dv.stale_drafts(releases, published="1.1.0") == ["v1.1.0rc3"]


def test_only_the_two_tag_shapes_the_workflow_makes_are_ever_removed() -> None:
    """`vX.Y.Z` and `vX.Y.ZrcN`; a draft of any other shape was made by someone else."""
    releases = [
        _draft("nightly"),
        _draft("v0.1.0-scratch"),
        _draft("1.0.0.dev-branch"),
        _draft("v0.2.0b1"),
        _draft("v0.2.0"),
        _draft("v0.2.0rc4"),
    ]
    assert dv.stale_drafts(releases, drafting="2.0.0") == ["v0.2.0", "v0.2.0rc4"]


def test_exactly_one_of_drafting_or_published_is_required() -> None:
    """Neither, or both, is a caller bug and must not pick a rule silently."""
    for kwargs in ({}, {"drafting": "1.0.0", "published": "v1.0.0"}):
        try:
            dv.stale_drafts([], **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"accepted {kwargs}")


def test_main_stale_drafts_mode(capsys, monkeypatch) -> None:
    """`--stale-drafts` with `--drafting` or `--published` prints one tag per line."""
    listing = json.dumps([_draft("v0.3.1rc1"), _draft("v0.4.0rc1")])
    monkeypatch.setattr("sys.stdin", _Stdin(listing))
    assert dv.main(["--stale-drafts", "--drafting", "0.4.0"]) == 0
    assert capsys.readouterr().out.split() == ["v0.3.1rc1"]
    monkeypatch.setattr("sys.stdin", _Stdin(listing))
    assert dv.main(["--stale-drafts", "--published", "v0.4.0"]) == 0
    assert capsys.readouterr().out.split() == ["v0.3.1rc1", "v0.4.0rc1"]
    monkeypatch.setattr("sys.stdin", _Stdin(listing))
    assert dv.main(["--stale-drafts", "--drafting", "0.4.0", "--pinned"]) == 0
    assert capsys.readouterr().out.split() == []


class _Stdin:
    """A stand-in for sys.stdin holding one string."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        """The whole string, as `sys.stdin.read()` would return it."""
        return self._text
