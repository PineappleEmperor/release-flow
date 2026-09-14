"""The commit-type vocabulary, parsed from each file that carries it."""

import importlib.util
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "commit_summary", _ROOT / "scripts/commit_summary.py"
)
cs = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(cs)

_GROUP = re.compile(r"\^\(([a-z|]+)\)")


def _alternation(text: str, after: str) -> set[str]:
    """The `^(a|b|c)` group of the first regex that follows `after` in `text`."""
    m = _GROUP.search(text, text.index(after))
    assert m, f"no ^(...) group after {after!r}"
    return set(m.group(1).split("|"))


def lint_types() -> set[str]:
    """The `types:` block lint-pr.yml hands to the title action."""
    text = (_ROOT / ".github/workflows/lint-pr.yml").read_text()
    block = text[text.index("types: |") + len("types: |") :]
    return {line.strip() for line in block.splitlines() if line.strip()}


def autolabeler_chore_types() -> set[str]:
    """The title types the drafter config labels `chore`."""
    text = (_ROOT / ".github/release-drafter.yml").read_text()
    return _alternation(text, 'label: "chore"')


def stale_step_chore_types() -> set[str]:
    """The title types the superseded-label step in pr-checks.yml maps to `chore`."""
    text = (_ROOT / ".github/workflows/pr-checks.yml").read_text()
    return _alternation(text, "Remove superseded type labels")


_TYPES = re.compile(r"\^\(?([a-z|]+)")


def _types_after(text: str, after: str) -> set[str]:
    """The types the first `^type` or `^(a|b)` regex after `after` in `text` accepts."""
    m = _TYPES.search(text, text.index(after))
    assert m, f"no ^type regex after {after!r}"
    return set(m.group(1).split("|"))


def test_the_autolabeler_labels_each_type_once() -> None:
    """The `fix` and `feature` rules accept only the type of that name, no alias."""
    text = (_ROOT / ".github/release-drafter.yml").read_text()
    assert _types_after(text, 'label: "fix"') == {"fix"}
    assert _types_after(text, 'label: "feature"') == {"feat"}


def test_the_stale_label_step_labels_each_type_once() -> None:
    """The step's fix and feat branches, which follow the chore and fix branches."""
    text = (_ROOT / ".github/workflows/pr-checks.yml").read_text()
    assert _types_after(text, "WIN=chore") == {"fix"}
    assert _types_after(text, "WIN=fix") == {"feat"}


def hook_types() -> set[str]:
    """The subject types the commit hook accepts."""
    text = (_ROOT / ".githooks/commit-msg").read_text()
    return _alternation(text, "# Subject shape.")


def test_the_title_allowlist_is_the_labelled_types() -> None:
    """lint-pr allows exactly what the autolabeler and the classifier map."""
    assert lint_types() == {"feat", "fix"} | set(cs.MAINT)


def test_the_autolabeler_folds_the_same_types_into_chore() -> None:
    """The drafter config's chore rule and the classifier's MAINT agree."""
    assert autolabeler_chore_types() == set(cs.MAINT)


def test_the_stale_label_step_folds_the_same_types_into_chore() -> None:
    """The removal step's chore fold agrees with the classifier's MAINT."""
    assert stale_step_chore_types() == set(cs.MAINT)


def test_the_hook_accepts_the_allowlist_plus_revert() -> None:
    """The hook accepts the lint-pr allowlist plus `revert`."""
    assert hook_types() == lint_types() | {"revert"}


def drafter_categories() -> dict[str, tuple[str, str]]:
    """Each drafter category as label -> (title, semver-increment)."""
    text = (_ROOT / ".github/release-drafter.yml").read_text()
    body = text[text.index("categories:") :]
    pattern = re.compile(
        r"- title: '(?P<title>[^']+)'\s+semver-increment: (?P<bump>\w+)\s+when:\s+"
        r"labels:\s+- '(?P<label>\w+)'"
    )
    found = {
        m.group("label"): (m.group("title"), m.group("bump"))
        for m in pattern.finditer(body)
    }
    assert found, "no categories parsed"
    return found


def test_the_drafter_categories_are_the_shared_vocabulary() -> None:
    """One category per managed label, titled and tiered as commit_summary.py says."""
    expected = {
        cs.LABEL_FOR[group]: (cs.HEADINGS[group], cs.BUMP_FOR[group])
        for group in cs.ORDER
        if group != "other"
    }
    assert drafter_categories() == expected
