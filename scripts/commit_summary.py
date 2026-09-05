#!/usr/bin/env python3
"""Group a PR's commit subjects by Conventional Commit type.

Also the one home of the release vocabulary the other scripts derive from.
"""

import argparse
import pathlib
import re
import sys

TYPE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<desc>.*)$"
)

# Types the release-drafter autolabeler folds into `chore` -> 🧰 Maintenance.
MAINT = frozenset({"chore", "docs", "refactor", "perf", "test", "build", "ci", "style"})

# The manifest/plugin version bump is release plumbing, not a changelog entry. The noun
# list stays closed on purpose: allowing arbitrary words before "to <semver>" would
# swallow every Dependabot bump, which is a real change and must reach the notes.
BUMP = re.compile(
    r"^[a-z]+(\([^)]*\))?:\s*bump\s+(the\s+)?"
    r"((manifest|plugin|integration|skill|marketplace|ha)\s+)*"
    r"(version\b|to\s+v?\d+\.\d+)",
    re.IGNORECASE,
)

# The release vocabulary: groups in severity order, the heading each takes in the
# notes, the label a PR of that group carries, and the semver tier that label resolves.
ORDER = ("breaking", "feat", "fix", "maint", "other")
HEADINGS = {
    "breaking": "🚨 Breaking Changes",
    "feat": "🚀 Features",
    "fix": "🔧 Fixes",
    "maint": "🧰 Maintenance",
    "other": "📦 Other",
}
LABEL_FOR = {
    "breaking": "xfeat",
    "feat": "feature",
    "fix": "fix",
    "maint": "chore",
    "other": "chore",
}
BUMP_FOR = {
    "breaking": "major",
    "feat": "minor",
    "fix": "patch",
    "maint": "patch",
    "other": "patch",
}
EMPTY_RANGE = "_No user-facing changes._"

# Suggested PR title type per winning commit group: (title, category, semver bump).
SUGGESTIONS = {
    "breaking": (
        "`feat!:` (or any `type!:`)",
        HEADINGS["breaking"],
        BUMP_FOR["breaking"],
    ),
    "feat": ("`feat:`", HEADINGS["feat"], BUMP_FOR["feat"]),
    "fix": ("`fix:`", HEADINGS["fix"], BUMP_FOR["fix"]),
    "maint": ("`chore:`", HEADINGS["maint"], BUMP_FOR["maint"]),
    "other": ("`chore:`", HEADINGS["maint"], BUMP_FOR["other"]),
}


def _strip_type(subject: str) -> str:
    """The description part of a Conventional Commit subject, lowercased."""
    m = TYPE.match(subject)
    return (m.group("desc") if m else subject).strip().lower()


def classify(subject: str) -> tuple[str, str]:
    """Return (group, description) for one commit subject."""
    m = TYPE.match(subject)
    if not m:
        return "other", subject.strip()
    desc = m.group("desc").strip()
    if not desc:
        # `feat:` with no description carries no information; keep the raw subject
        # so it is visible rather than rendering an empty bullet.
        return "other", subject.strip()
    if m.group("bang"):
        return "breaking", desc
    t = m.group("type").lower()
    if t in ("feat", "feature"):
        return "feat", desc
    if t == "fix":
        return "fix", desc
    if t in MAINT:
        return "maint", desc
    return "other", desc


def group(subjects: list[str]) -> dict[str, list[str]]:
    """Group non-plumbing subjects by type, preserving order within each group."""
    groups: dict[str, list[str]] = {k: [] for k in ORDER}
    for s in subjects:
        s = s.strip()
        if not s or BUMP.match(s):
            continue
        key, desc = classify(s)
        if desc not in groups[key]:  # a rebase can duplicate a subject verbatim
            groups[key].append(desc)
    return groups


def winning(subjects: list[str]) -> str:
    """Highest-impact group present — the title type a PR's commits imply."""
    groups = group(subjects)
    for key in ORDER:
        if groups[key]:
            return key
    return "maint"


# The types a PR title may carry: the two that label on their own and the eight that
# fold into `chore`. Any other commit type (`revert:`) is retyped `chore:` in a title.
LABELLABLE = frozenset({"feat", "fix"}) | MAINT

# The title-derived label is compared against the one the COMMITS entitle the PR to,
# which is what makes it correct rather than present.
MANAGED_LABELS = frozenset(LABEL_FOR.values())


def label_for(subjects: list[str]) -> str:
    """The one managed label these commits entitle the PR to."""
    return LABEL_FOR[winning(subjects)]


def title_for(subjects: list[str]) -> str:
    """A PR title for these commits: the winning group's oldest commit, verbatim.

    The winning group is a CHANGELOG CATEGORY (`maint` covers chore/docs/refactor/…),
    not a Conventional Commit type. Putting the category in a title produced `maint:`,
    which lint_pr rejects and the autolabeler maps to nothing. Take the type and the
    text from the same commit instead, so the title says what that commit said and
    stays labellable.
    """
    win = winning(subjects)
    for subject in subjects:
        m = TYPE.match(subject.strip())
        if not m or BUMP.match(subject.strip()) or classify(subject.strip())[0] != win:
            continue
        kind = m.group("type").lower()
        kind = "feat" if kind == "feature" else kind
        if kind not in LABELLABLE:
            kind = "chore"
        if m.group("bang"):
            kind += "!"
        return f"{kind}: {m.group('desc').strip()}"
    # No subject parses as the winning group; fall back to the first one, retyped.
    first = subjects[0].strip() if subjects else ""
    m = TYPE.match(first)
    return f"chore: {m.group('desc').strip() if m else first}"


def main() -> int:
    """Print the title, label or winning group for the subjects on stdin or in a file."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("winning", "title", "label"), default="title")
    ap.add_argument(
        "--subjects", default="-", help="file of commit subjects, or - for stdin"
    )
    args = ap.parse_args()

    if args.subjects == "-":
        subjects = sys.stdin.read().splitlines()
    else:
        with pathlib.Path(args.subjects).open(encoding="utf-8") as fh:
            subjects = fh.read().splitlines()

    if args.mode == "title":
        print(title_for(subjects))
    elif args.mode == "label":
        print(label_for(subjects))
    else:
        print(winning(subjects))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
