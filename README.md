# FireBuddy

An SMS wildfire assistant. Text it an address or town and it watches that place for
wildfires and official alerts, texts you first when something changes, and answers
questions in plain language ("should I leave?", "find me a shelter", "is the wind
pointing my way?"). See `PLAN.md` for the full design and `STATUS.md` for build
status, what's verified live, and what's blocked.

Every alert, guidance level, and safety claim in this app comes from deterministic
code and real data sources — the LLM only explains facts that tools already returned
and never decides whether to send an alert or what it says. See `PLAN.md` section 2.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` as you get keys (see "What's blocked" below). With nothing filled in,
everything still runs: data sources (geocoding, fires, NWS, shelters) are free and
need no key; the agent and real SMS are the only two pieces that need credentials.

## Tests and lint

```bash
pytest
ruff check .
```

135 tests, all offline — fixtures and a fake LLM client stand in for live APIs and
Claude, so the suite never costs money or depends on network access.

## Verify live data sources

```bash
PYTHONPATH=. python scripts/verify_phase1.py
```

Prints real fires, NWS alerts, wind, and shelters for a Danville, CA address, straight
from Census/NIFC/NWS/FEMA — no API key required.

## Demo: the console simulator

The fastest way to see the whole system work end to end, fully offline (fires, NWS
alerts, wind, shelters, and geocoding are all fixture-backed inside the simulator —
see `fixtures/`):

```bash
PYTHONPATH=. python sim.py
```

Chat as the simulated user, or use `:` commands to control the simulated world. Any
address you type resolves to the same fixture location (Danville, CA) — that's the
point, it's deterministic and offline. Try:

```
hi
3301 Camino Tassajara, Danville, CA
ADD 500 Diablo Rd, Danville, CA
LIST
STATUS
:fire Morgan 40 9 E
:wind 90 14 25
:nws redflag Red Flag Warning issued for Contra Costa County
:tick
:tick
:grow Morgan 150
:tick
:contain Morgan 100
:tick
:shelter Monte Vista HS Gym open
STATUS
:advance 3
STOP
LIST
START
HELP
:quit
```

The second `:tick` after setting up the fire sends nothing new — that's the dedupe
(`sent_alerts`) working. Type `:help` inside the simulator for the full command list.
If `ANTHROPIC_API_KEY` is set, free-form questions ("should I leave?", "is the wind
pointing my way?") go to the real agent; without it, they get a canned fallback that
points you back at the deterministic commands.

## Run the real app

```bash
uvicorn firebuddy.app:app --reload
```

- `GET /health` — liveness check.
- `POST /sms` — Twilio webhook. Verifies the Twilio signature unless `DRY_RUN=true`.
- A background task runs the monitor loop every `MONITOR_INTERVAL_SEC` seconds.

### Going live with real SMS (needs your own setup)

1. Buy/configure a Twilio number; set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_FROM_NUMBER` in `.env`.
2. `ngrok http 8000`, then set `PUBLIC_BASE_URL` to the ngrok URL and point the Twilio
   number's messaging webhook at `<PUBLIC_BASE_URL>/sms`.
3. Add your own phone number (E.164, e.g. `+15551234567`) to `SMS_ALLOWLIST`.
4. Set `DRY_RUN=false`.
5. Text the Twilio number.

Until all of that is done, `DRY_RUN=true` (the default) prints outbound messages to
the console instead of sending — safe by default, exactly as PLAN.md section 0
requires.

## Running real agent conversations

Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`, default
`claude-sonnet-5-5`) in `.env`. Then both `sim.py` and the `/sms` webhook route
free-form questions to the real model. Every agent turn is logged; inspect them with:

```bash
PYTHONPATH=. python -m firebuddy.traces --last 20
```

## Evals

```bash
PYTHONPATH=. python -m evals.run_evals
```

Runs the 10 scenarios in `evals/scenarios.py` against the real model (requires
`ANTHROPIC_API_KEY`), capped at `EVAL_MAX_TURNS` total agent turns. Without a key it
prints `BLOCKED` and exits non-zero rather than silently skipping. The harness itself
(world setup, turn budget, pass/fail checks) is covered by `tests/test_evals.py`
using a scripted fake LLM client, independent of whether a real key is present.

## What's blocked right now

See `STATUS.md` for the live detail. In short: everything is built and tested against
fixtures/fakes; what's missing is (1) `ANTHROPIC_API_KEY` for real agent conversations
and the eval suite, and (2) Twilio credentials + ngrok for a real SMS round trip.

## Layout

See `PLAN.md` section 7 for the full file-by-file breakdown.
