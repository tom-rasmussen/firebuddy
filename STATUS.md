# FireBuddy build status

## Live model verification (ANTHROPIC_API_KEY now set) — done
Ran the real `claude-sonnet-5-5` agent via `sim.py` for all five conversational
scenarios PLAN.md asks for, then the full eval suite.

- **`sim.py` against the real model:** "should I leave?", "is the wind pointing my
  way?", "find me a shelter", "watch my parents' place at 500 Diablo Rd Danville too",
  and "check back in 2 hours" — all five produced correct, fully-grounded replies
  (right guidance level, wind relation, shelter fallback messaging, a genuinely
  distinct second place, and a scheduled follow-up). No validator failures, no
  fallback-to-template responses.
- **`python -m evals.run_evals`: 10/10 scenarios passed, 0 ungrounded/failed-validator
  turns across all scenarios** (11 total agent turns, well under `EVAL_MAX_TURNS=60`).
- **Found and fixed two real bugs while running this — both from hitting the actual
  live API/data for the first time, not from anything the fake-client tests could
  have caught:**
  1. **Crash on extended-thinking responses.** `claude-sonnet-5-5` sometimes returns a
     `ThinkingBlock` alongside `tool_use`/`text` blocks (adaptive — it didn't appear
     on every turn, which is why this survived several turns before crashing on
     "watch my parents' place too"). `agent._block_to_dict()` only knew about
     `text`/`tool_use` and crashed with `AttributeError: 'ThinkingBlock' object has
     no attribute 'id'` trying to treat it as a tool call. Fixed by handling
     `thinking`/`redacted_thinking` block types explicitly (they must round-trip
     verbatim into the next assistant message, per Anthropic's extended-thinking +
     tool-use requirement) with a safe fallback for any other unrecognized type.
     Added a `ThinkingBlock` fake and a regression test
     (`test_run_turn_handles_thinking_blocks_alongside_tool_use`) so this is now
     covered without needing a live key.
  2. **Fake geocoding collapsed every address to one point.** `sim.py` forces
     `FIREBUDDY_FIXTURES` on for fully-offline geocoding (see prior polish entry
     below), but `fixtures/geocode.json` only had one real entry plus a catch-all
     `default` — so "500 Diablo Rd, Danville, CA" geocoded to the *same* lat/lon as
     Home. The real model correctly noticed this and refused to confirm it was
     watching a distinct "parents' place," which is honest, correctly-grounded
     behavior from the agent — but it defeated the demo. Fixed by adding a distinct
     `"diablo"` fixture entry near (but not identical to) Home; re-ran the scenario
     and the model now correctly reports a genuinely separate second place. Added a
     regression test (`test_geocode_fixture_diablo_is_distinct_from_default`).
- 157 tests total (2 new), all green; `ruff` clean.

## Post-MVP polish (from Tom's own sim run)
- **Local time instead of UTC.** `nws.get_timezone(lat, lon)` reads `properties.timeZone`
  off the already-cached NWS `/points` lookup (falls back to `DEFAULT_TIMEZONE =
  "America/Los_Angeles"` in fixture mode, on a missing field, or on any lookup error).
  `templates.format_time()` now converts to that zone and renders a real abbreviation
  ("11:48 PM PDT") via `zoneinfo` instead of "6:48 AM (UTC)". Added `tzdata` to
  `requirements.txt` so this doesn't depend on the host OS having a timezone database.
  `monitor.py` and `router.py` fetch the place's timezone once and thread it through
  every templated message.
- **No more duplicated alert text.** `official_alert_text()` now only prints the
  instruction/description line when it differs from the headline, instead of printing
  near-identical text twice (every NWS alert whose fields happen to be short enough to
  reuse the headline as the instruction was hitting this).
- **STATUS includes a wind line.** Extracted `agent.wind_for_place()` (previously
  duplicated inline in the `wind_check`/`assess_situation` tools) as the one shared
  place that fetches wind + resolves it against the nearest/named fire; `monitor.py`'s
  followup digest and `router.py`'s `STATUS` command now both call it and pass the
  result to a new `templates.wind_line()` ("Wind: from E at 14 mph (gusts 25), blowing
  from Morgan toward you (SIM obs, 11:48 PM PDT)."), flagging staleness when present.
- Caught and fixed a regression these changes introduced in `tests/test_monitor.py`:
  the new wind/timezone calls weren't mocked, so that test file would have made live
  NWS calls (works, since this sandbox has network access, but violates "never loop
  live calls in tests"). Fixed by extending its `sent_texts()` helper to fake
  `wind_data`/`get_timezone` like it already did for `fires_near`/`official_alerts`.
- 20 new/updated tests (`test_templates.py`, `test_nws_timezone.py`, plus additions to
  `test_monitor.py`/`test_router.py`/`test_sources_fixtures.py`): 155 total, all green;
  `ruff` clean. Re-ran the full `sim.py` demo transcript end to end to confirm all
  three fixes live in actual output (see commit for the transcript).

## Done
- **Phase 1 — DB, geo math, data clients.** `config.py`, `db.py` (SQLite schema + helpers,
  dedupe via unique `sent_alerts(place_id, key)`), `geo.py` (haversine, bearing, 16-pt
  compass, angular diff), `clock.py` (overridable `now()`), `sources/{geocode,fires,nws,shelters}.py`
  with live + fixture modes.
- **Phase 2 — Monitor, templates, dedupe.** `templates.py` (all deterministic message text:
  onboarding, new-fire, growth, containment, verbatim NWS alert with 480-char truncation,
  followup status digest). `monitor.py` `run_once(conn, send_fn)`: per active place, checks
  new fires, growth-threshold crossings (100/1k/10k/100k ac), containment, watched NWS
  alert types verbatim, and due follow-ups. Dedupe is solely via `sent_alerts` unique
  `(place_id, key)`; `incident_state.alerted_thresholds` tracks which growth thresholds a
  fire has already crossed so a newly-discovered fire that's already past a threshold
  doesn't immediately double-alert alongside its new-fire message.
- **Phase 3 — `assess_situation` + `wind_check`.** `assess.py`: pure functions
  `wind_relation` (toward ≤45°/crosswind ≤90°/away/light-variable <5mph/unknown),
  `wind_is_stale` (>2h), `wind_check` (composes a `wind_data()` result + bearing into the
  tool's full shape, always includes the terrain/ember caveat), and `assess_situation`
  (the 5-level table, highest match wins: LEAVE NOW → FOLLOW SHELTER ORDER → GET READY →
  BE READY → MONITOR). Added `bearing_deg` to `fires_near()`'s output (exact degrees, not
  just the 16-point compass label) since `wind_relation` needs it for the `angular_diff`
  math — a necessary addition to Phase 1's fires client, not a design deviation.
- **Phase 4 — Agent, tools, validator, traces.** `agent.py`: system prompt encoding section
  2's design rules; all 11 tools from section 5 (`list_places`, `add_place`, `remove_place`,
  `set_radius`, `fires_near`, `official_alerts`, `wind_check`, `assess_situation`,
  `find_shelters`, `schedule_followup`, `emergency_resources`) each ownership-checked against
  the calling user's places; a tool-use loop capped at 6 iterations/turn against a swappable
  `LLMClient` (`AnthropicLLMClient` for real use, `FakeLLMClient` scripted-response client for
  tests — per the spend guardrail, no real Anthropic calls happen in unit tests); a grounding
  validator (every non-time number must trace to this turn's tool results or the user's
  message; blocked safety/route phrases are only allowed verbatim-quoted from a tool result)
  with one retry then a deterministic status-template fallback; `agent_traces` logging via
  `db.log_trace`. `traces.py` CLI (`python -m firebuddy.traces --last N`).
- **Phase 5 — Router, Twilio webhook, simulator.** `router.py`: deterministic commands
  (ADD/LIST/REMOVE/RADIUS/STATUS/STOP/START/HELP, case-insensitive), an onboarding state
  machine on `users.state` (greet → capture address → geocode → confirm), STOP/START
  gating only free-form text (deterministic commands still work while opted out), and a
  graceful `AGENT_UNAVAILABLE_TEXT` fallback for free-form questions when no
  `ANTHROPIC_API_KEY`/LLM client is available. `sms.py`: `send()` (real Twilio only when
  `DRY_RUN=false` AND the recipient is in `SMS_ALLOWLIST`, dry-run console+outbox
  otherwise; a failed real send is caught and logged, never raised) and
  `verify_twilio_signature()`. `app.py`: FastAPI `POST /sms` (Twilio-signature-verified
  unless `DRY_RUN`), `GET /health`, and a lifespan-managed background task running
  `monitor.run_once()` every `MONITOR_INTERVAL_SEC`. `sim.py`: a console simulator that
  monkeypatches the fires/NWS/shelters clients to an in-memory world controlled by
  `:fire/:grow/:contain/:nws/:clearnws/:wind/:shelter/:tick/:advance <hrs>`, so the full
  onboarding → watch → alert → status → opt-out flow can be demoed with zero live
  dependencies except geocoding (left live and free). Added `python-multipart` to
  `requirements.txt` — FastAPI's `Form(...)` parsing requires it even for Twilio's
  URL-encoded webhook body; not a design deviation, just a missing transitive dependency
  caught by actually running the endpoint.
- **Phase 6 — Evals + README.** `evals/scenarios.py`: the 10 minimum scenarios from
  section 8 (each with its own fixed fires/alerts/wind/shelters world), each with a
  `check()` that inspects the actual tool-call results (e.g. `assess_situation`'s
  `level`) rather than fragile text-matching on the LLM's prose, plus cross-cutting
  checks (every turn's grounding validator passed, the mandatory 911/feel-unsafe line
  is present). `evals/runner.py`: installs each scenario's world via the same
  monkeypatch technique as `sim.py`, runs the real `agent.run_turn` per turn, and
  enforces `EVAL_MAX_TURNS` as a hard global cap across the whole suite (a
  `TurnBudgetExceeded` on scenario N aborts the run and records the remaining
  scenarios as failed rather than silently skipping them). `evals/run_evals.py`: CLI
  entry point; prints `BLOCKED` and exits non-zero if `ANTHROPIC_API_KEY` isn't set,
  rather than faking a result. `README.md`: setup, tests, live-check script, the
  simulator demo transcript, going-live steps for real SMS, running real agent
  conversations, evals, and trace inspection.
  - **Fixed a real bug found while building the evals**, not a test-writing mistake:
    `agent.validate()`'s number-grounding check flagged "911" (and would've flagged
    "211") as an ungrounded number, because the mandatory safety line the system
    prompt requires on every substantive reply ("call 911...") contains a digit that
    never appears in any tool result. Every single real agent turn would have failed
    grounding, retried, failed again, and fallen back to the deterministic template —
    i.e. the agent would never have produced a real LLM answer in practice. Fixed by
    exempting `{"911", "211"}` as safety constants in `agent.SAFE_NUMBER_CONSTANTS`
    (they're fixed values dictated by the system prompt, not situational facts that
    could be hallucinated wrong). Added a regression test
    (`test_validate_911_and_211_are_exempt_from_grounding`). This is exactly the kind
    of thing an eval suite is for — it surfaced from writing a scenario whose expected
    reply included the mandatory line, not from the unit tests (which hadn't included
    that line in their scripted replies).
  - Also made `sim.py`'s geocoding fixture-backed (`FIREBUDDY_FIXTURES` forced on in
    `install_fakes()` if not already set) so the simulator demo in the README runs
    fully offline, per section 0's definition of done ("the simulator demo in README
    works offline with fixtures") — Phase 5's live run above used real Census
    geocoding, which was correct for that phase's live-verification goal but not for
    the README's offline demo requirement.

## Verified live
- Geocoding: Census for `3301 Camino Tassajara, Danville, CA` → `(37.799428, -121.924274)`.
- Fires (NIFC WFIGS): query succeeds, 0 active WF incidents within 50 mi of that address right now.
- NWS alerts: query succeeds, 0 active alerts for that point right now.
- NWS wind: nearest station `F3625` (4.4 mi away); current observation is from 2026-10-22
  (stale, >2h — some ASOS stations report null `windDirection`/`windSpeed`/`windGust` on a
  given cycle, confirmed live). Hourly forecast returns cleanly. Phase 3's staleness check
  is designed for exactly this case.
- Shelters (FEMA NSS): query succeeds, 0 open shelters within 50 mi right now (no active
  disaster near Danville, as expected).
- Run `python scripts/verify_phase1.py` (with venv active) to re-check.
- `monitor.run_once()` run end-to-end against a real in-memory DB and the live fires/NWS
  clients for the Danville address: completes cleanly, 0 alerts sent (nothing active to
  alert on right now). Trigger/dedupe logic itself is covered by 9 unit tests with
  mocked source data (new fire → 1 alert; repeat → 0; growth threshold → 1; containment →
  1; NWS watched-event verbatim → 1 incl. exact instruction text; unwatched NWS event →
  0; due follow-up → status template + marked done).
- `assess.wind_check()` run live against real NWS wind data for the Danville address: the
  nearest station's latest observation is dated 2026-10-22 (several days old) with null
  speed/direction — `stale` correctly comes back `True`. 25 unit tests cover every
  guidance level and every wind relation (toward/crosswind/away/light-variable/unknown),
  plus staleness boundaries.
- Agent tools run live-shaped against fixtures (not real Claude, since there's no API key —
  see Blocked below): `assess_situation` on the fixture Morgan Fire (9 mi E, Red Flag Warning
  active) correctly returns GET READY; `wind_check` correctly returns `toward` (fixture wind
  is from the east, fire is east); `find_shelters` correctly filters out the closed fixture
  shelter. 29 unit tests cover every tool's ownership check and clamping, the full validator
  (grounded numbers pass, ungrounded numbers fail, clock times are ignored, blocked phrases
  fail unquoted and pass when quoted from a tool result), and `run_turn` end-to-end with a
  scripted `FakeLLMClient`: a plain tool-then-answer turn, a hallucinated-number reply that
  the validator catches and a retry recovers, a hallucinated reply that fails twice and falls
  back to the deterministic status template, and a run that hits the 6-tool-iteration cap.
- `sim.py` run end-to-end from a scripted stdin transcript (41 unit/integration tests for
  Phase 5 across `test_router.py`, `test_sms.py`, `test_app.py`, `test_sim.py` cover the
  pieces individually; this is the full-stack live run): "hi" → onboarding greeting →
  real Census-geocoded address ("123 Main St" fuzz-matched to the live TIGER-matched
  3301 Camino Tassajara) → confirmed watch; `ADD` a second real place; `LIST`/`STATUS`;
  `:fire`/`:wind`/`:nws redflag` then two `:tick`s — exactly one new-fire alert and one
  verbatim Red-Flag alert per place on the first tick, **zero** on the repeat (dedupe
  confirmed live through the real `monitor.run_once()` + `sent_alerts` table, not a mock);
  `:grow` past 100 ac → exactly one growth alert; `:contain` → exactly one containment
  alert; `:shelter ... open` + `STATUS` shows it; a free-form "should I leave?" correctly
  falls back to `AGENT_UNAVAILABLE_TEXT` (no API key); `:advance 3` moves the clock and
  ticks again; `STOP` silences free-form text but `LIST` still works; `START` reactivates;
  `HELP` lists commands. Found and fixed two sim-only parsing bugs while running this
  (multi-word shelter names, multi-word NWS event aliases) — real bugs, not flaky tests;
  fixed and covered them in `test_sim.py` before moving on.
- `evals/run_evals.py` run with no `ANTHROPIC_API_KEY` set: correctly prints
  `BLOCKED: set ANTHROPIC_API_KEY to run the live eval suite against the real model.`
  and exits non-zero (confirmed, see Blocked below). The harness mechanics themselves
  (world install/restore, per-scenario DB, turn-budget enforcement and abort-on-exceeded,
  pass/fail reporting) are exercised with a scripted `FakeLLMClient` in
  `tests/test_evals.py` — including a scenario that genuinely passes, one that
  genuinely fails on an unwanted phrase, the `watch_and_followup` scenario's
  add-place-then-schedule-followup multi-tool-call flow, and a turn-budget-exceeded
  abort with `EVAL_MAX_TURNS` monkeypatched to 1.

## Definition of done (against PLAN.md section 0)
- [x] All phases committed (one commit per phase, this one included).
- [x] `pytest` green: 157 tests, 0 failures, fully offline.
- [x] `ruff check .` green.
- [x] The simulator demo in the README works offline with fixtures (fires, alerts,
  wind, shelters, and geocoding are all fixture-backed inside `sim.py`).
- [x] Live data verified for a Danville, CA address (Phase 1's `scripts/verify_phase1.py`
  run against real Census/NIFC/NWS/FEMA; Phase 2/3's monitor and wind-staleness logic
  also run live against that same address).
- [x] Real agent + eval suite verified against the live Claude model (see top of this
  file) — the one piece that was blocked pending `ANTHROPIC_API_KEY`.
- [x] STATUS.md (this file) lists what's blocked and the exact steps to finish it.

## Deviations
- None from section 2/7 design rules. Added `scripts/verify_phase1.py` (not in the file list
  in section 7) purely as the live-check script Phase 1 asks for; it's not part of the
  app's runtime path.

## Blocked — exact steps to finish

One thing left, needs Twilio credentials only Tom has. `ANTHROPIC_API_KEY` is set and
live-verified (see above) — real agent conversations and the eval suite both work.

- **Twilio credentials + ngrok** (unlocks: a real SMS round-trip to Tom's phone).
  Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` in `.env`; run
  `ngrok http 8000`; set `PUBLIC_BASE_URL` to the ngrok URL and point the Twilio
  number's messaging webhook at `<PUBLIC_BASE_URL>/sms`; add Tom's own number
  (E.164) to `SMS_ALLOWLIST`; set `DRY_RUN=false`; run
  `uvicorn firebuddy.app:app --reload`; text the Twilio number.

Say "continue from STATUS.md" once that's set up and I'll run the live SMS
verification and append the results here.

## Next
- Nothing — the MVP (all 6 phases) is built, tested, and committed, and the agent is
  now verified against the real model. Twilio + ngrok above is the only thing left
  between this and a fully live demo on Tom's phone.
