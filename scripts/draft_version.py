#!/usr/bin/env python3
"""The version a release draft is held to while a prerelease line is open.

Usage:
    gh release list --exclude-drafts --json tagName,isPrerelease,publishedAt |
        draft_version.py                   # the base version, or nothing
    draft_version.py --base v1.2.0rc3      # 1.2.0
    gh release list --json tagName,isDraft |
        draft_version.py --stale-drafts (--drafting 1.2.0 | --published v1.2.0)
"""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest_gate as mg  # the one prerelease pattern and semver parser

# The only two tag shapes the workflow gives a draft: the full draft and its candidate.
_WORKFLOW_DRAFT = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)(?:rc[0-9]+)?$")


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


def stale_drafts(
    releases: list[dict],
    *,
    drafting: str | None = None,
    published: str | None = None,
    pinned: bool = False,
) -> list[str]:
    """The drafts to delete: below `drafting` on a push, at or below a published final.

    Exactly one of `drafting` and `published` is given. A pinned push, and a published
    tag that is not exactly its base once one leading `v` is removed, name nothing. Only drafts of the two shapes the
    workflow makes are ever named, compared as versions. Why each rule, is
    `release-drafter.yml` under *The five workflows* in the README.
    """
    if (drafting is None) == (published is None):
        raise ValueError("give exactly one of drafting or published")
    if published is not None:
        if published.removeprefix("v") != base(published):
            return []
        kept = mg.parse_semver(base(published))
    else:
        if pinned:
            return []
        kept = mg.parse_semver(base(str(drafting)))
    stale = []
    for release in releases:
        tag = release.get("tagName", "")
        match = _WORKFLOW_DRAFT.match(tag)
        if not release.get("isDraft") or not match:
            continue
        version = (int(match[1]), int(match[2]), int(match[3]))
        if (version <= kept) if published is not None else (version < kept):
            stale.append(tag)
    return stale


def main(argv: list[str] | None = None) -> int:
    """Print the pinned version, a version's base, or the drafts a release line has left."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", help="print this version's base and exit")
    ap.add_argument(
        "--stale-drafts",
        action="store_true",
        help="read `gh release list --json tagName,isDraft` and print the drafts to delete",
    )
    rule = ap.add_mutually_exclusive_group()
    rule.add_argument("--drafting", metavar="BASE", help="a push drafting BASE")
    rule.add_argument("--published", metavar="TAG", help="TAG was just published")
    ap.add_argument(
        "--pinned",
        action="store_true",
        help="with --drafting: the version came from the pin, so delete nothing",
    )
    args = ap.parse_args(argv)
    if args.base:
        print(base(args.base))
        return 0
    if args.stale_drafts:
        text = sys.stdin.read().strip()
        listing = json.loads(text) if text else []
        for tag in stale_drafts(
            listing,
            drafting=args.drafting,
            published=args.published,
            pinned=args.pinned,
        ):
            print(tag)
        return 0
    text = sys.stdin.read().strip()
    releases = json.loads(text) if text else []
    print(pinned_version(releases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
