# FireBuddy web demo: technical plan

Implements [spec.md](spec.md) under [constitution.md](constitution.md).

## Architecture

One Cloudflare Worker serves both the static UI and a small JSON API. No database: the scenario is a pure function of the step number, and test-mode results stay in the browser.

```
Browser (public/: index.html, app.js, styles.css)
   │  GET /            → Workers Static Assets
   │  GET /api/step/:n → baseline alert + FireBuddy alerts + assessment
   │  POST /api/ask    → deterministic answer + decision trace
   ▼
Worker (src/index.ts)
   ├─ rate limiter binding (RATE_LIMITER) on /api/*
   ├─ scenario/morgan.ts   stateAt(n): fires, alerts, wind, shelters (SIMULATED)
   ├─ engine/geo.ts        haversine, bearing, compass, angular diff
   ├─ engine/assess.ts     wind relation, staleness, readiness level
   ├─ engine/templates.ts  alert and reply text
   └─ engine/answer.ts     intent router: leave / wind / shelter / status / help
```

## Engine port

`geo.ts`, `assess.ts` and `templates.ts` are line-for-line ports of `firebuddy/geo.py`, `assess.py` and `templates.py`.
`scripts/export_golden.py` runs the Python engine over about 20 cases and writes `worker/test/golden.json`; the TypeScript tests must produce identical output (constitution gate 2).

Time formatting uses `Intl.DateTimeFormat` with the place's IANA zone in place of `zoneinfo`.

## API

| Route | Input | Output |
|---|---|---|
| `GET /api/scenario` | none | Step count and a title for each step |
| `GET /api/step/:n` | step 0–6 | `baseline` (county alert text or null), `alerts` (new FireBuddy alerts at this step), `assessment` (level, guidance, facts), `clock` |
| `POST /api/ask` | `{ step, question }` | `reply`, `trace` (`intent`, `decidedBy`, `level`, `sources`) |

Alert dedupe is computed, not stored: an alert appears at step n only if its event key did not exist at step n − 1 (AC-1, AC-2).

## Intent router (no LLM)

Keyword and phrase matching, in priority order: leave / evacuate / safe → readiness; wind → wind; shelter / evacuation center / where go → shelters; status / update → status; anything else → help text listing the suggested questions. "Am I safe?" maps to readiness and never answers yes (AC-9).

## Security

- `ratelimits` binding: about 120 requests per 60 s per IP (a page load is ~8 calls; testers may share Wi-Fi) on `/api/*` (AC-15).
- No secrets are needed for the demo.
- Strict input validation on `/api/ask`: step must be an integer in range; the question is trimmed to 200 characters.

## Testing

Vitest with `@cloudflare/vitest-pool-workers`. Every test name starts with the AC it proves, for example `AC-5: evacuation order always gives LEAVE NOW`.

## Deploy

`npx wrangler deploy` from `worker/`, using Tom's Cloudflare account (Cloudflare for Students).
