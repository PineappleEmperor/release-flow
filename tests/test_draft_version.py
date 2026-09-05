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


def test_a_final_as_the_newest_release_pins_nothing() -> None:
    """Newest published release `v1.0.0`, with an older rc behind it."""
    releases = [
        {"tagName": "v1.0.0", "isPrerelease": False},
        {"tagName": "v1.0.0rc1", "isPrerelease": True},
    ]
    assert dv.pinned_version(releases) == ""


def test_no_published_release_pins_nothing() -> None:
    """An empty list, as a repository with only drafts returns."""
    assert dv.pinned_version([]) == ""


def test_an_rc_line_after_a_final_pins_the_rc_base() -> None:
    """`v2.0.0rc3` newest, `v1.4.0` behind it."""
    releases = [
        {"tagName": "v2.0.0rc3", "isPrerelease": True},
        {"tagName": "v1.4.0", "isPrerelease": False},
    ]
    assert dv.pinned_version(releases) == "2.0.0"


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


class _Stdin:
    """A stand-in for sys.stdin holding one string."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        """The whole string, as `sys.stdin.read()` would return it."""
        return self._text
