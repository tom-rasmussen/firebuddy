# FireBuddy build status

## Done
- **Phase 1 — DB, geo math, data clients.** `config.py`, `db.py` (SQLite schema + helpers,
  dedupe via unique `sent_alerts(place_id, key)`), `geo.py` (haversine, bearing, 16-pt
  compass, angular diff), `clock.py` (overridable `now()`), `sources/{geocode,fires,nws,shelters}.py`
  with live + fixture modes.

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

## Deviations
- None from section 2/7 design rules. Added `scripts/verify_phase1.py` (not in the file list
  in section 7) purely as the live-check script Phase 1 asks for; it's not part of the
  app's runtime path.

## Blocked
- Nothing yet. Phase 4 (agent) needs `ANTHROPIC_API_KEY`; Phase 5 (real SMS) needs Twilio
  credentials. Neither is set — will build both against fixtures/stubs and mark blocked
  there, per section 0.

## Next
- Phase 2: monitor loop, templates, dedupe.
