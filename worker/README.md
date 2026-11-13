# FireBuddy web demo (Cloudflare Workers)

A browser demo of FireBuddy that replays a simulated fire, so it runs without SMS or API keys.
Spec and rules: [`../specs/firebuddy-worker/`](../specs/firebuddy-worker/).

Independent concept, not affiliated with Watch Duty.

## Run locally

```bash
cd worker
npm install
npm run dev        # http://localhost:8787
npm test           # unit + parity tests
npm run typecheck
```

## Parity with the Python build

The engine in `src/engine/` is a line-for-line port of `firebuddy/geo.py`, `assess.py` and
`templates.py`. To regenerate the golden file after changing the Python engine:

```bash
cd ..                                  # repo root, with the Python venv active
PYTHONPATH=. python scripts/export_golden.py
cd worker && npm test
```

## Deploy

```bash
npx wrangler login
npx wrangler deploy
```
