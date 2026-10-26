# FireBuddy build status

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

## Deviations
- None from section 2/7 design rules. Added `scripts/verify_phase1.py` (not in the file list
  in section 7) purely as the live-check script Phase 1 asks for; it's not part of the
  app's runtime path.

## Blocked
- **Phase 4 live verification — needs `ANTHROPIC_API_KEY`.** The agent is fully built and
  tested against a fake LLM client + fixtures (see above), but no real Claude conversation
  has been run (section 8's "Simulator: 'should I leave,' 'find a shelter,' ... all work"
  demands the real model). The actual conversation flows this requires are already proven
  via `run_turn` + `FakeLLMClient` tests; once a key is set, re-run with
  `agent.AnthropicLLMClient()` to confirm against the live model and append the transcript
  here. Model: `claude-sonnet-5-5` per `ANTHROPIC_MODEL`.
- **Phase 5 real SMS round-trip — needs Twilio credentials** (`TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `PUBLIC_BASE_URL`/ngrok). Router, webhook, and
  simulator are fully built and tested against the console/dry-run SMS backend (see above);
  what's missing is an actual text round-tripping through Twilio to Tom's phone. To finish:
  set the four Twilio env vars in `.env`, run `ngrok http 8000`, set `PUBLIC_BASE_URL` to
  the ngrok URL, point the Twilio number's webhook at `<PUBLIC_BASE_URL>/sms`, add Tom's
  number to `SMS_ALLOWLIST`, set `DRY_RUN=false`, then `uvicorn firebuddy.app:app --reload`
  and text the Twilio number.

## Next
- Phase 6: evals + README.
