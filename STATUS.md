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
- **Phase 5 real SMS — needs Twilio credentials** (`TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `PUBLIC_BASE_URL`/ngrok). Will build router +
  webhook + simulator fully against a console/stub SMS backend and mark the real round-trip
  blocked, per section 0.

## Next
- Phase 5: router + Twilio webhook + simulator.
