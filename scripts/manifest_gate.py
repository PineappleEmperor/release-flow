"""Decide whether a PR's manifest version is a valid bump for its label."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commit_summary as cs  # the one table of labels and the tier each resolves

Version = tuple[int, int, int]
_PRERELEASE = re.compile(r"(rc|alpha|beta|a|b|dev)[0-9]*$", re.IGNORECASE)
# Highest tier first, so a PR carrying two managed labels resolves the larger bump.
_TIER_RANK = {"major": 0, "minor": 1, "patch": 2}
_TIER_FOR_LABEL = {cs.LABEL_FOR[group]: cs.BUMP_FOR[group] for group in cs.ORDER}


def is_prerelease(version: str) -> bool:
    """Whether the version carries a PEP 440 prerelease suffix."""
    return _PRERELEASE.search(version) is not None


def parse_semver(version: str) -> Version:
    """The (major, minor, patch) triple, tolerating a prerelease suffix."""
    match = re.match(
        r"^([0-9]+)\.([0-9]+)\.([0-9]+)", version
    )  # de-anchored: tolerate rcN
    if not match:
        raise ValueError(f"cannot parse version: {version!r}")
    return int(match[1]), int(match[2]), int(match[3])


def label_bump(labels: list[str]) -> str | None:
    """The semver tier the PR's labels imply, or None when none is managed."""
    tiers = [_TIER_FOR_LABEL[lab] for lab in labels if lab.lower() in _TIER_FOR_LABEL]
    return min(tiers, key=_TIER_RANK.__getitem__) if tiers else None


def _bump(base: Version, tier: str) -> Version:
    major, minor, patch = base
    if tier == "major":
        return (major + 1, 0, 0)
    if tier == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def _fmt(version: Version) -> str:
    return "v{}.{}.{}".format(*version)


def evaluate(
    last_release: str,
    main_version: str,
    pr_version: str,
    labels: list[str],
    *,
    dependabot: bool = False,
    breaking_commits: int | None = None,
) -> tuple[bool, str]:
    """Whether pr_version is a valid bump for the labels, and why."""
    if dependabot:
        return True, "dependabot exempt"

    # Label (from the title) and commits must agree about being breaking. Not called by
    # the shipped stack, which uses only --suggest; kept for a repo that gates a
    # committed version, and correct only once the PR's labels are reconciled.
    if breaking_commits is not None:
        claims_breaking = label_bump(labels) == "major"
        if claims_breaking and breaking_commits == 0:
            return False, (
                "PR title marks a breaking change but no commit does. "
                "The notes are built from commits, so this majors with an "
                "empty Breaking Changes section. Mark the commit `type!:`."
            )
        if not claims_breaking and breaking_commits > 0:
            return False, (
                f"{breaking_commits} commit(s) marked `type!:` but the PR "
                "title does not, so this ships a breaking change without a "
                "major bump. Retitle the PR `type!:` or drop the `!`."
            )
    base = parse_semver(last_release or "0.0.0")
    if is_prerelease(pr_version):
        if pr_version == last_release:
            return False, f"prerelease v{pr_version} must differ from last release"
        return True, "prerelease differs from last release"
    pr = parse_semver(pr_version)
    if pr == base:
        # A final graduating its own rc line parses to the same triple.
        if is_prerelease(last_release):
            return True, f"final v{pr_version} graduates prerelease {last_release}"
        return False, f"manifest v{pr_version} == last release; bump it"
    tier = label_bump(labels)
    if tier is None:
        return True, "no managed label; version only needs to differ from last release"
    floor = _bump(base, tier)
    if pr < floor:
        return False, f"{tier} needs >= {_fmt(floor)}, got v{pr_version} (under-bumped)"
    main = parse_semver(main_version) if main_version else floor
    ceiling = max(floor, main)
    if pr > ceiling:
        return (
            False,
            f"v{pr_version} exceeds the justified bump (expected <= {_fmt(ceiling)} for {tier})",
        )
    return True, "ok"


def main(argv: list[str] | None = None) -> int:
    """Print the verdict, or with --suggest the version the labels imply."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last-release", required=True)
    parser.add_argument("--main-version", default="")
    parser.add_argument("--pr-version", default="")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="print the version the labels imply and exit",
    )
    parser.add_argument("--labels", default="", help="comma-separated label names")
    parser.add_argument("--dependabot", action="store_true")
    parser.add_argument(
        "--breaking-commits",
        type=int,
        default=None,
        help="count of commits whose subject carries a Conventional "
        "Commit `!` marker; omit to skip the consistency check",
    )
    args = parser.parse_args(argv)
    labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    if args.suggest:
        # No label that maps to an increment means no release is implied at all,
        # which is different from implying a patch.
        tier = label_bump(labels)
        base = parse_semver(args.last_release)
        print(_fmt(_bump(base, tier)) if tier else _fmt(base))
        return 0
    if not args.pr_version:
        parser.error("--pr-version is required unless --suggest is given")
    ok, reason = evaluate(
        args.last_release,
        args.main_version,
        args.pr_version,
        labels,
        dependabot=args.dependabot,
        breaking_commits=args.breaking_commits,
    )
    print(("✅ " if ok else "❌ ") + reason)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
