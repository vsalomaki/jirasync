# Local Jira for testing

A throwaway Jira Data Center instance to develop the fetch and write layers
against, so neither real instance is touched while the code is still wrong.

Runs on `127.0.0.1:8180`, bound to loopback only. Container names and the port
are chosen not to collide with anything else on the box.

## Start it

```
docker compose -f docker/compose.yml up -d
docker compose -f docker/compose.yml logs -f jira
```

First boot takes several minutes while Jira builds its schema. The healthcheck
polls `/status` and reports healthy once it returns `RUNNING`.

## What can come from the environment, and what cannot

Copy `.env.example` to `.env` and run:

    docker compose --env-file docker/.env -f docker/compose.yml up -d

**Settings: yes.** The database configures itself from `ATL_JDBC_*`, so the
wizard never asks for it. Port, image tag, database credentials and JVM sizing
come from `.env`. Anything the image does not expose directly can still be
written into `jira-config.properties` through numbered
`ADDITIONAL_JIRA_CONFIG_NN` variables, with a `__EXPAND_ENV` suffix if a value
needs a secret substituted from another variable.

**Licence and administrator account: no.** The image's entrypoint has no
handling for either. Both are written to the database by the setup wizard, so
there is no variable to set. The remaining manual steps are therefore:

1. **Application properties.** Title and base URL. Anything is fine.
2. **Licence.** A free 30 day Data Center evaluation key from `my.atlassian.com`,
   which needs an Atlassian account. Jira will not leave `FIRST_RUN` without it.
3. **Administrator account.** Local and disposable.
4. **Mail notifications.** Skip.

Driving that wizard over HTTP is possible in principle, but its XSRF handling
and multi step form dispatch made it unreliable enough not to ship. Snapshot the
result instead, below, which makes the wizard a one time cost rather than
something to automate.

Then create a personal access token: profile menu, Personal Access Tokens,
Create token. That is the same auth path as the real instances (ADR-006).

Point the connectivity probe at the instance with that token in
`JIRASYNC_TOKEN`, the same way it is pointed at a real instance.

## Make setup a one time cost

Once the wizard is done, snapshot the volumes. Restoring skips setup entirely,
including the licence, so a rebuild costs seconds rather than another trip to
`my.atlassian.com`.

    docker compose -f docker/compose.yml stop
    docker run --rm -v jirasync-test_jira:/from -v "$PWD/docker/snapshot":/to \
      alpine tar czf /to/jira.tgz -C /from .
    docker run --rm -v jirasync-test_db:/from -v "$PWD/docker/snapshot":/to \
      alpine tar czf /to/db.tgz -C /from .

Restore by reversing the mounts into a fresh pair of volumes. `docker/snapshot/`
is gitignored: it contains the licence and the admin account.

### Before the licence is entered

`GET /rest/api/2/serverInfo` answers `503` with `text/html`, not JSON. That is
worth knowing twice over: it explains why the probe fails if run too early, and
it is a ready-made fixture for the content type assertion the backend needs,
since it reproduces the "REST endpoint returned HTML" case without having to
build an SSO proxy to cause it.

## What this can and cannot answer

Useful for the questions that are about **Jira's behaviour**:

- whether `/rest/api/2/issue/{key}/changelog` exists on this version, or whether
  `expand=changelog` capped at 100 histories is the only route
- whether user objects carry a stable `key` alongside `name`
- what `fields=*all` actually returns, and what a changelog entry looks like
- that writes, transitions, comments and attachment upload behave as expected
- that the backend layer handles pagination, retries and error shapes

Useless for the questions that are about **your data**, because this instance
has none of it:

- whether the external id field holds a peer issue key or an id from some
  earlier system
- what format historical external id values are in
- whether an SSO proxy sits in front of `/rest` on the real instance

Those still need the real instances. This only removes the excuse for testing
the code against them.

## Match the real version

The compose file pins `9.12`, which currently resolves to 9.12.38, to match the
deployed Data Center line. If the real instances move, change the tag and
rebuild: the changelog endpoint question above is version dependent, and
answering it against the wrong version answers nothing.

## Tear down

```
docker compose -f docker/compose.yml down          # keep the data
docker compose -f docker/compose.yml down -v       # and delete it
```

The volumes hold the licence and the admin account, so `down -v` means going
through the wizard again.
