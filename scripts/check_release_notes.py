#!/usr/bin/env python3
"""Check the release body a reader actually gets; each check names its problem.

Usage:
    check_release_notes.py --tag v1.2.3        # a published or draft release
    check_release_notes.py --file notes.md     # a local file
"""

import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import commit_summary as cs  # the sentinel and the headings the notes are built from

ENTRY = re.compile(r"^- (?P<title>.+?) @\S+ \(#(?P<pr>\d+)\)\s*$")
TYPE_PREFIX = re.compile(r"^[a-zA-Z]+(\([^)]*\))?!?:\s*")
DRAFTER_CONFIG = pathlib.Path(".github/release-drafter.yml")
EMPTY_RANGE = cs.EMPTY_RANGE
BREAKING_HEADING = cs.HEADINGS["breaking"]


def placeholder_from(config: pathlib.Path) -> str | None:
    """The drafter config's `template` block."""
    if not config.is_file():
        return None
    lines = config.read_text(encoding="utf-8").splitlines()
    block: list[str] = []
    for i, line in enumerate(lines):
        if re.match(r"^template:\s*\|", line):
            for follow in lines[i + 1 :]:
                if follow.strip() and not follow.startswith((" ", "\t")):
                    break
                block.append(follow.strip())
            break
    text = "\n".join(block).strip()
    return text or None


def check(
    notes: str,
    version: str | None = None,
    placeholder: str | None = None,
    *,
    first_release: bool = False,
) -> list[str]:
    """Return a list of problems; empty means the notes are well formed."""
    problems: list[str] = []

    # A major with nothing under Breaking Changes.
    if version and not first_release:
        major = version.lstrip("v").split(".")[0]
        minor_patch = version.lstrip("v").split(".")[1:]
        if (
            major.isdigit()
            and int(major) > 0
            and minor_patch[:2] == ["0", "0"]
            and BREAKING_HEADING not in notes
        ):
            problems.append(
                f"{version} is a major release with no Breaking Changes section; "
                "mark the breaking commit `type!:`, not just the PR title"
            )
    # The empty-range sentinel.
    if notes.strip() == EMPTY_RANGE:
        problems.append(
            "release body is the empty-range sentinel; the previous tag resolved to the "
            "release being written, so the whole changelog was dropped"
        )

    # The drafter config's template, or nothing at all.
    body = notes.strip()
    if not body or (placeholder and body == placeholder):
        problems.append(
            "release body is the draft placeholder; no push ever wrote notes to it"
        )

    # release-drafter's own body: one line per PR with an @author.
    if any(ENTRY.match(line.strip()) for line in notes.splitlines()):
        problems.append(
            "release body is release-drafter's PR-per-line output; the type-grouped "
            "generator never overwrote it"
        )

    # A bullet repeating the section heading it sits under.
    section: str | None = None
    for line in notes.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        text = line.strip().lstrip("- ").strip()
        plain = re.sub(r"[*_`]", "", text).strip().lower()
        if section and plain and plain == section:
            problems.append(f"bullet repeats its section heading: {text!r}")

    return problems


def main() -> int:
    """Check one release body, from a tag or a file, and report every problem."""
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--tag", help="release tag to fetch with gh")
    src.add_argument("--file", help="local markdown file")
    ap.add_argument(
        "--version", help="version being released, to check major/breaking agreement"
    )
    ap.add_argument(
        "--config",
        default=str(DRAFTER_CONFIG),
        help="drafter config whose `template` is the draft placeholder",
    )
    ap.add_argument(
        "--first-release",
        action="store_true",
        help="no full release precedes this one; skip the major/breaking check",
    )
    args = ap.parse_args()

    if args.tag:
        out = subprocess.run(
            ["gh", "release", "view", args.tag, "--json", "body", "--jq", ".body"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode:
            sys.exit(f"could not read release {args.tag}: {out.stderr.strip()}")
        notes = out.stdout
    else:
        with pathlib.Path(args.file).open(encoding="utf-8") as fh:
            notes = fh.read()

    problems = check(
        notes,
        args.tag or args.version,
        placeholder_from(pathlib.Path(args.config)),
        first_release=args.first_release,
    )
    if not problems:
        print("release notes render correctly")
        return 0
    for p in problems:
        print(f"::error::{p}")
    print(
        f"\n{len(problems)} problem(s). The notes are what users read; fix them before publishing."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
