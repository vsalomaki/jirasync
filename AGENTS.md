# AGENTS.md

Conventions for anyone working in this repo, human or agent.

## What this is

One-way Jira → Jira issue sync over a self-contained bundle file. Two deployment
shapes (`split`, one process per end; `direct`, one process reaching both) and two
transports (a directory, or a network endpoint later). Air-gapped operation is the
demanding case it is built for, not the whole of it.

**Design only. No code yet.** Read the design documents and the decision log
before starting an implementation phase or changing anything structural.

## The decision log is append-only

22 ADRs record why this is shaped the way it is. They are the reasoning, not just
the outcome, and ADR numbers below are stable identifiers into that log.

- **Supersede, never rewrite.** Add a new ADR and leave a pointer on the old one
  (`**Amended by ADR-0NN.**`). An ADR that recorded a decision genuinely held is
  history; editing it to match a later view falsifies the record.
- Every ADR states what it **costs**, not only what it decided. An entry with no
  cost paragraph is not finished.
- Reference ADRs by number from code comments and docs. Numbers are permanent.

## Invariants that are easy to break

These are settled, and each has an ADR behind it. Reintroducing any of them is a
regression even when it looks like a simplification.

- **Flow is one-way**, source → destination, direction declared in config and not
  on the CLI. There is no return bundle and no acknowledgement (ADR-019).
- **There is no `sync_id`.** An issue is identified by its source key, which the
  destination stores in its external-id field. The UUID was removed on purpose:
  it made a lost source database create duplicates (ADR-021).
- **Base advances only on a successful write or an explicit operator judgement.**
  Never on a failed write, a deferral, or a converged no-op. Each of those loses
  data silently (ADR-020).
- **The scrub validator is a blocking gate**, never a warning and never skippable
  per run. It greps the serialised bundle, and a hit means no bundle is written
  (ADR-009). Whether it runs at all is deployment policy (ADR-016).
- **Matching proposes, never binds.** A false negative is a duplicate issue fixed
  by hand; a false positive fuses two unrelated issues permanently, with no undo
  (ADR-008).
- **Scope is enforced on import as well as export.** Without it the tool is an
  arbitrary write channel into the destination (ADR-011).

Unresolved design questions live in the open-questions document, and move to repo
issues once the design stops moving.

## Never commit

- `config/*.yaml`, except `*.example.yaml`. Live config carries hostnames, field
  IDs and instance details.
- State databases, bundles, raw dumps, quarantine, transport directories, scrub
  and adoption reports. All gitignored; check `.gitignore` before adding a path
  that produces artifacts.
- Tokens. Auth is `token_env` pointing at an environment variable, never inline.

`*.complete-platform.json` files **are** committed. They are the machine-readable
record of a supported release target (ADR-014).

## Commits

**Prefer `git commit --amend` to a follow-up commit.** While a change is unpushed,
fold corrections into the commit they belong to rather than leaving a trail of
fixups behind them. History should read as one commit per coherent change, and a
commit that needed three attempts is not a coherent change. It is one change and
two mistakes.

Explain *why* in the message. What changed is in the diff; what it cost and what
it rules out is not.

Changes reach `main` through a pull request, never a direct push. Work on a
branch, open a PR, let the checks run. `main` is protected: linear history, no
force pushes, review threads resolved before merge, and rebase is the only merge
method, which is why the commits on a branch are worth curating before it opens.

Never push, open a PR, or file an issue without being asked for that specific
action.

## Stack

Python 3.11+. `httpx`, `pydantic` v2, `typer`, `rich`, `textual`, `PyYAML`,
`sqlite3`, `zipfile`. Jira Data Center API v2, wiki markup, `startAt` pagination,
PAT bearer auth.

- **Do not use `pycontribs/jira`.** It abstracts away the parts that need control.
- Release targets are Linux x86_64 and Windows x86_64. **Open every bundle member
  in binary mode and write `\n` explicitly.** Windows text mode turns them into
  `\r\n` and `SHA256SUMS` stops matching across platforms.
- Assert `content-type: application/json` on every response. An SSO-fronted Jira
  returns a 200 HTML login page rather than a 401.

## Tests

Write them first for the two places a bug is unrecoverable: the scrubber and the
merge function. The output validator must be
tested against a deliberately un-scrubbed bundle and must fail it. A validator
that has never failed anything is not known to work.

## Prose and formatting

The docs are written to be read, and reviewed as carefully as code.

- Inline comments in `config/*.example.yaml` align at **column 37**.
- ASCII diagrams are padded to equal width. Regenerate them programmatically
  rather than counting spaces by hand.
- No issue or PR numbers in comments. State what is true now, not how it got
  that way. That belongs in the commit message.
- No em dashes, in comments, commit messages or documents. Close the sentence and
  start another, or use a colon when the second half explains the first.
