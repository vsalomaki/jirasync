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

## Finish setup by hand

The database configures itself. Jira reads the `ATL_JDBC_*` variables in the
compose file, writes its own `dbconfig.xml` and runs the first-run upgrade tasks
without anyone touching the wizard, so the database step never appears.

What is left is the browser wizard at `http://localhost:8180`, which opens on
"Set up application properties":

1. **Application properties.** Title and base URL. Anything is fine.
2. **Licence.** Jira will not leave `FIRST_RUN` without one. A free 30 day Data
   Center evaluation key comes from `my.atlassian.com` and needs an Atlassian
   account. This is the only step that cannot be done offline.
3. **Administrator account.** Local and disposable.
4. **Mail notifications.** Skip.

Then create a personal access token: profile menu, Personal Access Tokens,
Create token. That is the same auth path as the real instances (ADR-006).

Point the connectivity probe at `http://localhost:8180` with that token in
`JIRASYNC_TOKEN`, the same way it is pointed at a real instance.

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
