# Fork notes: jeph/hermes-talk

This is a fork of [TheSmokeDev/hermes-talk](https://github.com/TheSmokeDev/hermes-talk).
It is installed as the `hermes-talk` Hermes plugin from this fork, so
`hermes plugins update hermes-talk` pulls from `origin` (this fork), not upstream.

- `origin`: `git@github.com:jeph/hermes-talk.git`
- `upstream`: `https://github.com/TheSmokeDev/hermes-talk.git`
- Forked from upstream `64ede8f` (v0.21.1).

Every intentional difference from upstream is listed below. When you merge
upstream, keep each one unless its "drop when" condition is met. When you add a
new difference, add an entry here in the same commit.

## Differences from upstream

### 1. Discord voice auto-join

Hermes joins one configured Discord voice channel and starts the same session
`/talk join` starts whenever a Talk operator is in that channel. It stops the
session and leaves once no operator remains. Every human join or leave on that
channel, and every gateway reconnect, re-checks this rule; so while an operator
is present, any such event restarts a session that has ended (for example after
`/talk leave`). A channel with only non-operators never gets a session.

| Setting | Meaning |
|---|---|
| `TALK_AUTOJOIN_VOICE_CHANNEL_ID` | Numeric ID of the voice channel to watch. Unset or non-numeric means the feature is off. |
| `TALK_DISCORD_OPERATOR_USER_IDS` | Upstream's existing operator list; the same IDs decide who triggers auto-join. |

Files:

- `talk_autojoin.py` (new): the whole feature. It registers a Discord
  platform-handler factory through the host's `ctx.register_platform_handler`,
  adds an `on_voice_state_update` listener with `bot.add_listener` so the host's
  own handler stays intact, joins with the adapter's `join_voice_channel`, and
  starts or stops Talk with `talk_discord.start_session` and `stop_session`. It
  reads `talk_discord._SESSION` to tell whether a session is live, because
  upstream has no public accessor for that.
- `__init__.py`: `talk_autojoin` in both import blocks and one
  `talk_autojoin.register(ctx)` call at the end of `register()`.
- `pyproject.toml`: `talk_autojoin` in `py-modules` and in isort's
  `known-first-party`.
- `tests/test_autojoin.py` (new).

Preserve when merging: the `register()` call, the two import lines, and the
`pyproject.toml` entries. If upstream renames or reshapes `talk_discord._SESSION`,
`start_session`, `stop_session`, or `talk_config.discord_operator_user_ids`,
update `talk_autojoin.py` to match; `tests/test_autojoin.py` fails if they drift.

Drop when: upstream ships its own auto-join for Discord voice. Then delete
`talk_autojoin.py`, its test, and the lines above, and move the setting to
upstream's name.

### 2. api_server catalog listings accept the `data` envelope

The Hermes api_server answers `GET /v1/skills` and `GET /v1/toolsets` with
`{"object": "list", "data": [...]}`. Upstream's `talk_apiserver._listing` only
accepted a bare list or `{"skills": [...]}` / `{"toolsets": [...]}`, so the
toolsets read failed. Because the capability catalog is all-or-nothing, Talk then
reported that no capabilities were available and the voice model refused to
hand off work.

Files: `talk_apiserver.py` (`_listing` also accepts a list under `data`) and
`tests/test_apiserver_lane.py` (`test_listings_accept_the_api_servers_data_envelope`).

Drop when: upstream `_listing` accepts the `data` envelope.

### 3. The capability catalog waits for the first api_server probe

At session start, upstream warms the capability catalog before it warms the
api_server lane check. The catalog's first read therefore saw the lane's cold
"still checking" answer and cached "no capabilities" for 30 seconds
(`TALK_CAPABILITY_CATALOG_TTL_S`). The voice model was told nothing was
available and refused to hand off work.

Files: `talk_capabilities.py` (`_from_api_server` calls the blocking
`talk_apiserver.warm()` when the cached lane answer is the cold
`CHECKING_DETAIL` one; that function only runs on the catalog's refresh thread
or inside the already-blocking `warm()`) and `tests/test_capabilities.py`
(`test_a_cold_lane_verdict_is_probed_before_the_catalog_gives_up`).

Drop when: upstream resolves the lane before the catalog's first read, or no
longer caches a cold lane verdict as the catalog.

### 4. In-process catalog uses Hermes's current skill helper names

Hermes renamed `tools.skills_tool._find_all_skills` / `_sort_skills` to
`find_all_skills` / `sort_skills` (hermes-agent `93fafc4d6f`). Upstream's
in-process catalog tier imported only the old names, failed silently (debug
log), and fell through to the api_server over HTTP even inside the gateway.

Files: `talk_host.py` (`_catalog_from_host_modules` imports the public names and
falls back to the underscored ones for older hosts) and
`tests/test_capabilities.py`
(`test_in_process_tier_reads_the_current_public_skill_helpers`).

Drop when: upstream imports the public names.

### 5. The session-start catalog wait no longer blocks the event loop

`run_talk_session` is a coroutine; in the Discord lane it runs on the gateway's
event loop, which also serves Hermes's api_server. Upstream called the blocking
`talk_capabilities.wait_until_warm` (up to `TALK_CATALOG_STARTUP_WAIT_S`, 2.5 s)
directly, so the catalog's HTTP read of the api_server (1.5 s probe timeout)
could not be answered until the wait ended, and the failure was cached.

Files: `talk_cli.py` (`await asyncio.to_thread(talk_capabilities.wait_until_warm, ...)`)
and `tests/test_cli.py` (`test_the_startup_catalog_wait_leaves_the_event_loop_free`).

Drop when: upstream stops blocking the loop for that wait.

## Related local patch outside this repo

Hermes Agent itself (`~/.hermes/hermes-agent`, not this repo) carries one local
edit that the capability catalog depends on: `gateway/platforms/api_server.py`
`_handle_skills` called `find_all_skills(skip_disabled=False, include_editorial=True)`,
but `include_editorial` was removed from `tools/skills_tool.py` by upstream's
Collective Wisdom revert (`0dcadf6f41`), so `/v1/skills` always returned 500. The
local edit drops that argument. A Hermes update can overwrite it; if
`GET /v1/skills failed` reappears in `~/.hermes/logs/gateway.log`, reapply it or
check whether upstream fixed it.

## Merging upstream

```bash
git fetch upstream
git merge upstream/main          # merge, not rebase: this fork's main is pushed
# resolve conflicts, keeping every difference listed above
uvx ruff==0.17.1 check .         # version pinned in requirements-lint.txt
.venv/bin/python -m pytest -q    # venv: uv venv --python 3.14 .venv && uv pip install --python .venv -e ".[dev]"
git push origin main
hermes plugins update hermes-talk
hermes gateway restart           # a running gateway keeps the old code until restarted
```

After merging, re-check each "Drop when" condition above and update this file.
