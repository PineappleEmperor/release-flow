#!/usr/bin/env python3
"""Every reusable workflow this repository ships must be called by the testbed.

Goal (6) of the delivery model says a release of a CI repository is proven on the testbed
before it is tagged. Nothing enforced it, and `ha-panel-ci` was tagged `v1.0.0` while no
repository anywhere called its one reusable workflow; the first call, weeks later, failed
twice in two minutes. This is that goal, mechanised: a workflow with no caller has never
run, and a release containing it is a claim rather than a result.

Usage, from a checkout of the repository being judged:
    gh api "repos/<owner>/ha-ci-testing/contents/.github/workflows" --jq '.[].name' |
        while read -r f; do
            gh api "repos/<owner>/ha-ci-testing/contents/.github/workflows/$f" --jq .content |
                base64 -d
        done | testbed_coverage.py --repo <owner>/<this-repo> --workflows .github/workflows
"""

import argparse
import pathlib
import re
import sys

import yaml

# `uses: owner/repo/.github/workflows/name.yml@ref`, the only shape a caller may take.
# YAML lets the value be quoted, and the quotes are optional here because a caller this
# misses is reported as never called, which is the worst verdict the check can reach.
CALL = re.compile(
    r"uses:\s*[\"']?(?P<repo>[\w.-]+/[\w.-]+)/\.github/workflows/(?P<file>[\w.-]+\.ya?ml)@"
)


# A `#` and the rest of its line. Caller text is matched as text rather than parsed, so a
# commented-out caller would otherwise count as a real one and invert the failure this
# exists to catch. The version comment on a real pin sits past the `@`, where the match
# has already ended, so stripping it changes nothing.
COMMENT = re.compile(r"#.*")


# A reusable workflow no integration is meant to call, so the testbed never will. It says
# so in its own text rather than being special-cased here: an exception a reader cannot see
# in the file is one nobody maintains. `testbed-coverage.yml` is the first of them.
EXEMPT = "# testbed-coverage: not-for-consumers"


def reusable(workflows: pathlib.Path) -> list[str]:
    """The filenames in `workflows` that declare `on: workflow_call` and are for consumers."""
    found = []
    for wf in sorted(workflows.glob("*.y*ml")):
        try:
            text = wf.read_text(encoding="utf-8")
            doc = yaml.safe_load(text) or {}
        except OSError, yaml.YAMLError:
            continue
        if EXEMPT in text:
            continue
        # PyYAML reads a bare `on:` key as the boolean True, so both spellings are checked.
        triggers = doc.get(True) if doc.get(True) is not None else doc.get("on")
        # `on:` takes a mapping, a list or a bare string. A form not recognised here is a
        # workflow dropped from the list silently, and so never judged at all.
        if isinstance(triggers, str):
            triggers = [triggers]
        if isinstance(triggers, dict | list) and "workflow_call" in triggers:
            found.append(wf.name)
    return found


def called(text: str, repo: str) -> set[str]:
    """The workflow files of `repo` that the concatenated caller text calls."""
    return {
        m.group("file")
        for m in CALL.finditer(COMMENT.sub("", text))
        if m.group("repo").lower() == repo.lower()
    }


def uncovered(workflows: pathlib.Path, callers: str, repo: str) -> list[str]:
    """Reusable workflows this repository ships that the testbed never calls."""
    return sorted(set(reusable(workflows)) - called(callers, repo))


def main(argv: list[str] | None = None) -> int:
    """Report any reusable workflow the testbed does not call; exit 1 if there is one."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name of the repository judged")
    ap.add_argument("--workflows", default=".github/workflows")
    ap.add_argument(
        "--testbed", default="the testbed", help="named in the message only"
    )
    args = ap.parse_args(argv)

    workflows = pathlib.Path(args.workflows)
    if not workflows.is_dir():
        print(f"❌ FAIL: {workflows} is not a directory")
        return 1
    text = sys.stdin.read()
    if not text.strip():
        print(f"❌ FAIL: read no caller workflows from {args.testbed} — NOT CHECKED")
        return 1

    missing = uncovered(workflows, text, args.repo)
    for name in missing:
        print(
            f"❌ FAIL: {name} is reusable and {args.testbed} never calls it, so no release "
            f"of it has ever run"
        )
    if not missing:
        print(f"✅ every reusable workflow is called by {args.testbed}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
