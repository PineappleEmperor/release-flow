#!/usr/bin/env python3
"""The version a release draft is held to while a prerelease line is open.

Usage:
    gh release list --exclude-drafts --json tagName,isPrerelease,publishedAt |
        draft_version.py                   # the base version, or nothing
    draft_version.py --base v1.2.0rc3      # 1.2.0
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest_gate as mg  # the one prerelease pattern and semver parser


def base(version: str) -> str:
    """The `major.minor.patch` of a version, without any prerelease suffix."""
    return "{}.{}.{}".format(*mg.parse_semver(version.lstrip("v")))


def pinned_version(releases: list[dict]) -> str:
    """The base of the newest candidate, but only where no full release exists at all.

    release-drafter counts full releases alone as "the last release", so a repository whose
    whole published history is candidates has nothing to resolve from and drafts `v0.0.1`.
    This supplies the number for that one case. The moment a full release exists the labels
    on the PRs merged since it are the answer, and an override can only contradict them —
    a repository with `v7.2.0` released and `v7.2.1rc1` open would otherwise have drafted
    `v7.2.1` for two breaking changes.

    Among candidates the newest is the one published last. An rc and its final draft are
    created in the same run, so creation order says nothing about which came out first.
    """
    # The workflow has already asked GitHub whether a full release exists, without a
    # window; this repeats the question over whatever list it was handed so the function
    # is right on its own, and so a caller that skips that step cannot get a wrong number.
    if not releases or any(not r.get("isPrerelease") for r in releases):
        return ""
    newest = max(releases, key=lambda r: r.get("publishedAt") or "")
    return base(newest["tagName"])


def main(argv: list[str] | None = None) -> int:
    """Print the pinned version from a release list on stdin, or a version's base."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", help="print this version's base and exit")
    args = ap.parse_args(argv)
    if args.base:
        print(base(args.base))
        return 0
    text = sys.stdin.read().strip()
    releases = json.loads(text) if text else []
    print(pinned_version(releases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
