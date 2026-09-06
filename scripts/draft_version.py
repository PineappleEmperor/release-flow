#!/usr/bin/env python3
"""The version a release draft is held to while a prerelease line is open.

Usage:
    gh release list --exclude-drafts --limit 20 --json tagName,isPrerelease,publishedAt |
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
    """The base of the most recently published release when it is a prerelease, else ""."""
    if not releases:
        return ""
    newest = max(releases, key=lambda r: r.get("publishedAt") or "")
    if not newest.get("isPrerelease"):
        return ""
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
