# release-flow

One home for a Conventional Commits release pipeline, for any repository that uses
Conventional Commits. The sections below say what the five reusable workflows do, how a
consumer calls them, and how a release of this repository reaches consumers.

## The five workflows

All five are reusable (`on: workflow_call`) and live in `.github/workflows/`.
Four of them are a consumer's PR and release plumbing, and their jobs keep the
`name:` the source stack used, because those names are the required status-check
contexts on a consumer's ruleset. The fifth is not for consumers at all: it is
what the three CI repositories run on themselves. Four of the five also
check out this repository a second time, into `.release-flow`, at the SHA the
caller pinned; checking out with `path:` cleans only that directory, so it
never disturbs the tree already checked out above it, and the scripts run
against the Python floor this repository declares in `pyproject.toml`'s
`target-version`, since the runner's own `python3` predates it.

**`pr-checks.yml`** — every PR-time job that reads or writes labels, in one
workflow so `needs:` can order them; a `labeled`/`unlabeled` trigger cannot
substitute, because GitHub suppresses events caused by the default
`GITHUB_TOKEN`, so the autolabeler's own label would never wake a follow-on
workflow, and consumers previously raced or polled for it instead. Deliberately
not here: `lint-pr` and any hacs/hassfest/python/quality-audit checks a
consumer runs, since none of them read or write labels and folding them in
would only couple unrelated failures. `label` (*CC labelling*) runs the
release-drafter autolabeler from the PR title and removes any superseded type
label — the autolabeler only adds, so a PR retitled mid-life (`fix` to `feat`)
would otherwise keep the old label and list under two release-drafter
categories. `title-check` (*CC label validation*) is the gate: it reads the
PR's commit subjects over the API, asks `commit_summary.py` which label those
commits entitle the PR to, and fails with a comment naming the right title when
the label the PR carries disagrees. Once the label is right it withdraws the
comment and writes the implied next version to the step summary via
`manifest_gate.py --suggest`. It checks out nothing of the consumer. Its caller's
trigger must be `pull_request_target`, since a fork PR gets a read-only token under
`pull_request` and could not be labelled or commented on; running in the base repo's
context with a writable token means nothing here may execute PR-authored code, which
is why neither job checks out the PR head.

**`lint-pr.yml`** — *CC title validation*: `action-semantic-pull-request` with the
ten types the autolabeler maps, and only those. `revert:` is deliberately absent
because it maps to no label and would leave a PR with no release category.

**`auto-draft-pr.yml`** — *Auto draft PR*: on a push to any non-default branch by
the repository owner, opens a draft PR titled from the branch's commits
(`commit_summary.py --mode title`), trusting the title because the commit-msg
hook already validated those commits. Gated to the owner because the PR is
opened with the release token and would otherwise appear to be authored by
whoever owns it; everyone else opens their own PR. It checks out full history,
since the title is built from the commit range ahead of the default branch,
and skips when a PR is already open for the branch or there are no commits
ahead of it. See The one secret.

**`release-drafter.yml`** — *Auto draft releases*: on a push to the default branch
runs release-drafter, which resolves the version from the merged PRs' labels —
each carries a semver-increment and the highest one since the last release
wins — and maintains a draft; nothing in this repository carries a
hand-written version, and a consumer that needs the number in a file writes it
there when the release publishes. release-drafter counts only full releases as
"the last release", so a repository whose most recently published release (by publish
time, since an rc and its final are created together) is a prerelease
would resolve from nothing and draft `v0.0.1`; `draft_version.py` therefore holds
the draft to that line's base version while it is open (`v1.0.0rc1` keeps the draft
at `v1.0.0`), and the labels take over again once a full release exists. Publishing a
prerelease thereby fixes the number its final will carry; a larger change starts a
new line. It checks out the consumer's full history,
since `release_notes.py` walks a `tag..HEAD` range a shallow clone can't
resolve, then that script writes a body grouped by commit type over the
drafter's PR-per-line body — release-drafter categorises by PR label, so a fix
inside a feat-titled PR would file under Features, where grouping by the type
of change (how HACS repos are surveyed to do it) would not. Notes are measured
from commits since the last full release, not the newest release of any kind,
so every rc shows the cumulative set that will ship and the final shows the
complete set; the release being written is excluded from that lookup so it
cannot match itself on publish. A full draft and an rc draft are kept alive
together: publishing either is a real release, never a rebuild, and reusing
the rc draft while it stays unpublished keeps rc numbers tracking published
candidates instead of incrementing on every push; both draft tags are built
from the release's base version, since appending the rc suffix to an
already-resolved prerelease version once doubled it (`v0.1.0rc1rc1`). The New
Contributors section comes from GitHub's own generate-notes endpoint, since
"first contribution" is its definition to begin with. `check_release_notes.py`
fails the job if the body a reader would see is a placeholder, the
empty-range sentinel, the drafter's own output, a major with no Breaking
Changes section, or a bullet that repeats its own heading. `release: published` fires last for both the
draft-published and the tag-pushed paths, so on that event the workflow writes
the final body once, last, and deletes the superseded drafts — left behind, an
rc draft would reappear in the release list for a version that already
shipped and keep being updated by the next push. Writing the body with
`gh release edit` fires `edited`, not `published`, so the job never retriggers
itself.

**`testbed-coverage.yml`** — *Every reusable workflow is called by the testbed*: for a
CI repository, not for an integration. It reads the testbed's caller workflows over the
API and fails when a workflow this repository ships with `on: workflow_call` is named by
none of them. The rule is older than the check — a release of a CI repository is proven on
the testbed before it is tagged — and `ha-panel-ci` was tagged `v1.0.0` with nothing
anywhere calling its one workflow. Its first call, arranged weeks later, failed twice in
two minutes. A workflow with no caller has never run, and a release containing it is a
claim rather than a result. Reading no callers at all fails too, since an empty answer and
full coverage are otherwise the same result. A reusable workflow no integration is meant
to call — this one is the first — says so with a `# testbed-coverage: not-for-consumers`
line of its own, rather than being named in an exception list a reader of the workflow
would never see.

## Calling the workflows

A consumer carries one caller workflow per reusable workflow in its own
`.github/workflows/`, under the same filename. A caller is the trigger, the
`permissions:` the reusable workflow needs (a called workflow can only downgrade what
its caller grants), a short job id, and a `uses:` line pinned to a commit SHA with the
matching tag in a comment. These four are an integration's callers, complete:

```yaml
# .github/workflows/pr-checks.yml
name: PR Checks

on:
  pull_request_target:
    types: [opened, reopened, synchronize, edited]

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: pr-checks-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  pr:
    uses: PineappleEmperor/release-flow/.github/workflows/pr-checks.yml@{{sha}} # {{tag}}
```

```yaml
# .github/workflows/lint-pr.yml
name: Lint PR

on:
  pull_request_target:
    types: [opened, edited, synchronize, reopened]

permissions: {}

jobs:
  lint:
    permissions:
      pull-requests: read
    uses: PineappleEmperor/release-flow/.github/workflows/lint-pr.yml@{{sha}} # {{tag}}
```

```yaml
# .github/workflows/auto-draft-pr.yml
name: Draft PR

on:
  push:
    branches-ignore: [main]

permissions:
  contents: read

jobs:
  draft:
    uses: PineappleEmperor/release-flow/.github/workflows/auto-draft-pr.yml@{{sha}} # {{tag}}
    secrets:
      release-token: ${{ secrets.RELEASE_TOKEN }}
```

```yaml
# .github/workflows/release-drafter.yml
name: Release Drafter

on:
  push:
    branches: [main]
  release:
    types: [published]

permissions:
  contents: write
  pull-requests: write

jobs:
  release:
    uses: PineappleEmperor/release-flow/.github/workflows/release-drafter.yml@{{sha}} # {{tag}}
```

A CI repository adds a fifth, which an integration does not carry:

```yaml
# .github/workflows/testbed-coverage.yml
name: Testbed Coverage

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  coverage:
    uses: PineappleEmperor/release-flow/.github/workflows/testbed-coverage.yml@{{sha}} # {{tag}}
```

`{{tag}}` is the newest full release of this repository and `{{sha}}` the commit it
points at; nothing stored anywhere carries them, so nothing drifts:

```
TAG=$(gh api repos/PineappleEmperor/release-flow/releases/latest --jq .tag_name)
SHA=$(gh api "repos/PineappleEmperor/release-flow/commits/$TAG" --jq .sha)
```

From then on Dependabot moves the SHA and the comment together. A `{{` left in a
consumer's workflow is an audit failure. The `pr-checks` caller also carries the
`concurrency` group and the event `types` list, because both are keyed on the
triggering event and belong with the trigger. `labeled`/`unlabeled` are deliberately
excluded from those `types`: as `pr-checks.yml` above notes, those events never fire
for the labels this pipeline applies; they do fire for Dependabot's three-at-once
labels, which once started five runs within two seconds, and `cancel-in-progress`
cancelling four of them left the rollup FAILURE with nothing actually broken, making
the PR unmergeable.

## The one secret

`auto-draft-pr.yml` declares `secrets: release-token: {required: true}` and its
caller passes `secrets: release-token: ${{ secrets.RELEASE_TOKEN }}`, a
repository secret holding a PAT or app token with contents and pull-requests
write. It is needed because a PR opened with the default `GITHUB_TOKEN` fires no
`pull_request_target` event, so no checks would run and the required contexts
would never report; the PR would be permanently unmergeable, which is how the
previous auto-PR workflow failed. The other four
workflows use the consumer's own `GITHUB_TOKEN`, which a called workflow receives
automatically, and nothing is passed with `secrets: inherit`.

## Check names

A check-run produced by a called workflow is named `<caller job id> / <called job
name>`. With the job ids of the callers above the required contexts are:

| Caller job | Check-run name |
|---|---|
| `pr` | `pr / CC labelling` |
| `pr` | `pr / CC label validation` |
| `lint` | `lint / CC title validation` |
| `draft` | `draft / Auto draft PR` |
| `release` | `release / Auto draft releases` |

Keep the first three required on the default branch; they report three different
failures. `CC title validation` catches a title whose type is not in the
allowlist, `CC labelling` catches the labelling machinery failing, and
`CC label validation` catches a label that exists but is wrong, which is the case
a `fix:`-titled PR carrying a `feat!:` commit produced: labelled `fix`, filed under
Fixes, released as a patch. `draft` and `release` are not PR contexts.

## Versions

A tag on this repository is a version of the pipeline, drafted by the same
`release-drafter.yml` it ships. Consumers pin as Calling the workflows shows, the shape
Dependabot understands for GitHub Actions, so a release here arrives at every consumer
as its existing weekly grouped Dependabot PR. Inside a called workflow `github.job_workflow_sha` is that
pinned commit, and every script is checked out from it, so a consumer runs
scripts and workflow from the same commit and can say which version it runs by
reading the comment. In a local call (this repository's own `pr.yml`, `draft-pr.yml`
and `release.yml`) the same expression resolves to this repository's own commit.

## Called versus copied

Called, never copied: the five reusable workflows and `scripts/`. Copied into the
consumer, because nothing can call them: the four caller workflows an integration carries;
`.github/release-drafter.yml`, which the drafter action reads from the consumer's
own default branch over the API and which carries the autolabeler rules and the
label-to-semver mapping; and `.githooks/commit-msg`, enabled per clone with
`git config core.hooksPath .githooks`, which rejects subjects that are not
Conventional Commits, subjects that join two changes with `and`, editorialising
words, AI-attribution trailers, and `BREAKING CHANGE:` footers (`!` on the type is
the only breaking marker). The consumer's Dependabot configuration needs a `github-actions`
ecosystem entry for the pin to move; `.github/dependabot.yml` here is the shape
to copy. The reusable workflows are callable from another repository only while
this one is public or the consumer's token can read it.

## This repository's own checks

`.github/workflows/ci.yml` runs `ruff check`, `ruff format --check` and pytest on
`scripts/` and `tests/` under `pyproject.toml`, whose `[tool.ruff]` tables are the
ones every consumer carries. Consumers never run it; they run the scripts
through the reusable workflows. `tests/` covers `commit_summary.py`,
`manifest_gate.py`, `release_notes.py`, `draft_version.py` and `testbed_coverage.py`;
`check_release_notes.py` has no test
file of its own and is exercised only through `test_release_notes.py`, which loads
it by path. `test_vocabulary.py` reads the commit-type lists out of `lint-pr.yml`,
the drafter config, the stale-label step, the commit hook and `commit_summary.py`,
and fails when any two disagree, since none of them can import another. Locally, where
`python3` must itself meet the floor named under The five workflows, since the scripts
use syntax an older interpreter cannot parse:

```
python3 -m pip install -r requirements.test.txt
ruff check . && ruff format --check . && python3 -m pytest -q
```
