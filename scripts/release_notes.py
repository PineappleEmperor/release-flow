#!/usr/bin/env python3
r"""Generate release notes grouped by commit type.

Output shape:

    ## 🚀 Features

    - add powerwall mode select for charging ([#1216](…/pull/1216))

    ## 🔧 Fixes

    - strip whitespace from the region domain ([#3524](…/pull/3524))

    **Full Changelog**: [v1.2.0...v1.3.0](…/compare/v1.2.0...v1.3.0)

Usage:
    release_notes.py --range v1.2.0..HEAD --repo-url https://github.com/o/r \
                     --previous v1.2.0 --version 1.3.0
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commit_summary as cs  # same classifier the PR body uses

MERGE = re.compile(r"^Merge pull request #(?P<pr>\d+) ")
ORDER = cs.ORDER
HEADINGS = {key: f"## {title}" for key, title in cs.HEADINGS.items()}
EMPTY_RANGE = cs.EMPTY_RANGE


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), capture_output=True, text=True, check=True
    ).stdout


def pr_for(sha: str, head: str) -> str | None:
    """The PR a commit arrived with, from the merge commit that introduced it.

    git log is newest-first, so the introducing merge is the OLDEST containing it.
    Taking the first line instead credits every commit to the most recent merge.
    """
    out = subprocess.run(
        (
            "git",
            "log",
            "--merges",
            "--reverse",
            "--format=%s",
            f"{sha}..{head}",
            "--ancestry-path",
        ),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for line in out.splitlines():
        if m := MERGE.match(line):
            return m.group("pr")
    return None


def new_contributors(github_notes: str, *, include_bots: bool = False) -> str:
    """The `## New Contributors` block out of GitHub's own generated notes."""
    out: list[str] = []
    for line in github_notes.splitlines():
        if line.startswith("## "):
            if out:
                break
            if "New Contributors" not in line:
                continue
            out.append(line)
            continue
        if not out or not line.strip():
            continue
        # Only list items belong to the section. Require the space: the trailing
        # `**Full Changelog**` line is bold, not a heading, and `**` starts with the
        # same character as a bullet, so testing for "*" alone still swallowed it.
        if not line.lstrip().startswith(("* ", "- ")):
            break
        # GitHub counts bots. Thanking dependabot for its first contribution is
        # noise, not credit.
        if not include_bots and re.search(r"@[\w.-]+\[bot\]", line):
            continue
        out.append(line)
    # Filtering can empty the section: ha-lego's only new contributor for v1.0.0rc1
    # was dependabot, which left a bare heading with nothing under it.
    if len(out) < 2:
        return ""
    return "\n".join(out).rstrip()


def build(
    rev_range: str,
    repo_url: str | None = None,
    head: str = "HEAD",
    previous: str | None = None,
    version: str | None = None,
    github_notes: str | None = None,
    include_bots: bool = False,
) -> str:
    """The release body for rev_range: grouped subjects, contributors, compare link."""
    groups: dict[str, list[str]] = {k: [] for k in ORDER}
    seen: set[tuple[str, str]] = set()

    for line in _git("log", "--reverse", "--format=%H%x00%s", rev_range).splitlines():
        if "\0" not in line:
            continue
        sha, subject = line.split("\0", 1)
        if MERGE.match(subject) or cs.BUMP.match(subject):
            continue
        key, desc = cs.classify(subject)
        if (key, desc) in seen:  # a rebase can replay a subject verbatim
            continue
        seen.add((key, desc))
        ref = ""
        if pr := pr_for(sha, head):
            ref = f" ([#{pr}]({repo_url}/pull/{pr}))" if repo_url else f" (#{pr})"
        groups[key].append(f"- {desc}{ref}")

    out: list[str] = []
    for key in ORDER:
        if groups[key]:
            out += [HEADINGS[key], "", *groups[key], ""]

    if not out:
        return EMPTY_RANGE

    if github_notes and (
        block := new_contributors(github_notes, include_bots=include_bots)
    ):
        out += [block, ""]

    if repo_url and previous and version:
        tag = version if version.startswith("v") else f"v{version}"
        out.append(
            f"**Full Changelog**: [{previous}...{tag}]({repo_url}/compare/{previous}...{tag})"
        )

    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    """Print the release body for the range on the command line."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--range", required=True, help="git revision range, e.g. v1.2.0..HEAD"
    )
    ap.add_argument("--head", default="HEAD", help="tip used to resolve PR attribution")
    ap.add_argument("--repo-url", help="https://github.com/owner/repo, to link PRs")
    ap.add_argument("--previous", help="previous tag, for the compare link")
    ap.add_argument("--version", help="version being released, for the compare link")
    ap.add_argument(
        "--github-notes-file",
        help="body from POST /releases/generate-notes; its New "
        "Contributors section is spliced in",
    )
    ap.add_argument(
        "--include-bots",
        action="store_true",
        help="keep bot accounts in New Contributors",
    )
    args = ap.parse_args()
    gh_notes = None
    if args.github_notes_file:
        with Path(args.github_notes_file).open(encoding="utf-8") as fh:
            gh_notes = fh.read()
    print(
        build(
            args.range,
            args.repo_url,
            args.head,
            args.previous,
            args.version,
            github_notes=gh_notes,
            include_bots=args.include_bots,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
