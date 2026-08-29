# jirasync

One-way Jira → Jira issue synchronisation over a self-contained bundle file.

Two Jira Data Center instances that do not share a database. Issues are exported
from one, normalised into an instance-neutral bundle, and applied to the other
via REST.

Commercial Jira-to-Jira sync tools are webhook- or broker-driven and assume
continuous reachability between the instances, which rules them out wherever the
two sides are separated. Open-source options are one-off migration scripts rather
than repeatable sync.

**Status: design complete, no code yet.**

---

## Capabilities

- **One-way sync**, source → destination, with the direction fixed in
  configuration rather than chosen per run.
- **Three-way merge** against stored base values, so an incoming change that
  would overwrite an edit made on the destination is detected instead of applied.
- **Transport-agnostic.** The bundle is self-contained, hashed and schema
  stamped, so it can travel over a network endpoint or on removable media across
  an air gap without the pipeline knowing which.
- **Two deployment shapes.** `split` runs a process at each end, each holding
  only its own credentials; `direct` runs one process reaching both.
- **Instance-neutral canonical form.** Field IDs, values, statuses and users are
  mapped locally at each end against a shared vocabulary, so neither instance
  needs to know how the other is configured.
- **Link and URL scrubbing**, with a validator that greps the serialised bundle
  and refuses to write it on any hit.
- **Scope filtering** enforced on import as well as export, so an inbound bundle
  cannot reach issues outside what the receiving instance allows.
- **Single-artifact delivery** on Linux and Windows x86_64, dependencies
  vendored, with no install step on the receiving host.

## Shape of the thing

```
  ┌─ SOURCE ───────────────────┐            ┌─ DESTINATION ──────────────┐
  │ jirasync export            │            │                            │
  │   → raw-alpha-<ts>.zip     │            │                            │
  │ jirasync normalize         │            │                            │
  │   → bundle-alpha-<ts>.zip  │  ──bundle──▶ jirasync plan              │
  │                            │            │   → conflicts.json         │
  │                            │            │ jirasync resolve           │
  │                            │            │   → resolutions.json       │
  │                            │            │ jirasync apply             │
  │                            │            │   → writes                 │
  └────────────────────────────┘            └────────────────────────────┘
```

`export` and `normalize` are separate so a mapping error can be corrected from the
retained raw dump instead of re-reading Jira. `plan` and `apply` are separate so
everything unmapped fails before anything is written.

## Target environment

Jira Data Center at both ends: API v2, wiki markup, PAT bearer auth. Cloud is not
required, though the backend seam exists for it. The receiving host is assumed to
have Python 3.11+ and nothing else.

## Licence

MIT. See `LICENSE`.

Configuration files carry instance hostnames and field IDs, so only the
`.example.yaml` files are tracked. See `.gitignore`.
