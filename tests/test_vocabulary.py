"""The commit-type vocabulary, parsed from each file that carries it."""

import importlib.util
import pathlib
import re

import yaml

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


_DRAFTER_RULE = re.compile(r"/(?P<pattern>.*)/(?P<flags>[a-z]*)")
_STEP_BRANCH = re.compile(
    r"grep (?P<flags>(?:-[A-Za-z]+\s+)+)'(?P<pattern>[^']+)';\s*then WIN=(?P<label>\w+)"
)


def _compiled(pattern: str, flags: str) -> re.Pattern[str]:
    """The regex as the file's own engine would run it."""
    return re.compile(pattern, re.IGNORECASE if "i" in flags else 0)


def autolabeler_rules() -> dict[str, list[re.Pattern[str]]]:
    """Each autolabeler label -> the title regexes that apply it, compiled as written."""
    config = yaml.safe_load((_ROOT / ".github/release-drafter.yml").read_text())
    rules: dict[str, list[re.Pattern[str]]] = {}
    for rule in config["autolabeler"]:
        patterns = []
        for title in rule["title"]:
            m = _DRAFTER_RULE.fullmatch(title)
            assert m, f"not a /regex/flags title rule: {title!r}"
            patterns.append(_compiled(m["pattern"], m["flags"]))
        rules[rule["label"]] = patterns
    assert rules, "no autolabeler rules parsed"
    return rules


def stale_step_branches() -> list[tuple[str, re.Pattern[str]]]:
    """Each branch of the superseded-label step as (label, title regex), in order."""
    text = (_ROOT / ".github/workflows/pr-checks.yml").read_text()
    step = text[text.index("Remove superseded type labels") : text.index("CURRENT=")]
    found = [
        (m["label"], _compiled(m["pattern"], m["flags"]))
        for m in _STEP_BRANCH.finditer(step)
    ]
    assert len(found) == step.count("then WIN="), "a branch was not parsed"
    assert found, "no title branches parsed"
    return found


def test_the_autolabeler_labels_feat_titles_only_as_feat() -> None:
    """`feature:` is a label, not a title type: no rule applies any label to it."""
    rules = autolabeler_rules()
    assert any(r.match("feat: add thing") for r in rules["feature"])
    assert any(r.match("FEAT(scope): add thing") for r in rules["feature"])
    for label, patterns in rules.items():
        for pattern in patterns:
            assert not pattern.match("feature: add thing"), (label, pattern.pattern)


def test_the_stale_label_step_reads_feat_titles_only_as_feat() -> None:
    """The step's branches agree with the autolabeler about a `feature:` title."""
    branches = stale_step_branches()
    assert any(
        label == "feature" and pattern.match("feat: add thing")
        for label, pattern in branches
    )
    for label, pattern in branches:
        assert not pattern.match("feature: add thing"), (label, pattern.pattern)


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
