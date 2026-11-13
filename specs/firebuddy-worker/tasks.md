# FireBuddy web demo: tasks

Each phase is done only when its "done when" is true and the constitution's quality gates pass.

| # | Phase | ACs | Done when | When |
|---|---|---|---|---|
| 0 | Setup: `worker/` with Wrangler, TypeScript, Vitest, static assets, rate-limit binding | — | `wrangler dev` serves a placeholder page; `npm test` runs | Fri (tonight) |
| 1 | Engine port: geo, assess, templates + golden parity tests | AC-4, AC-5, AC-7 | TypeScript output matches the Python golden file exactly | Fri (tonight) |
| 2 | Replay scenario: 7 SIMULATED steps of the Morgan Fire | AC-1, AC-2, AC-3, AC-10 | Expected readiness level asserted at every step; no alert repeats | Sat |
| 3 | API + intent router + rate limiting | AC-6, AC-8, AC-9, AC-11, AC-15 | Integration tests cover every route and the 429 | Sat |
| 4 | Web UI: baseline / FireBuddy / PM panels, controls, disclaimer | AC-10, AC-11, AC-12, AC-16 | Full demo runs in `wrangler dev` and at phone width | Sat |
| 5 | Test mode: baseline vs FireBuddy, decision timing, copy results | AC-13, AC-14 | A full run in each mode produces copyable results | Sat |
| 6 | Package: README rewrite, worker README, STATUS.md | — | `npm test` green; `wrangler deploy --dry-run` succeeds | Sat |
| 7 | Tom: deploy, phone check, one pilot session | — | Live URL works; pilot fixes applied | Sat |
| 8 | Tom: user test with 5 people | — | Results copied for each participant | Sun |
| 9 | Case study written around real results | — | Doc complete with real numbers and links | Sun |

## Later (not this weekend)

- "Check a real address" mode using live NIFC and NWS data
- Live LLM answers behind the same validator
- SMS delivery once carrier registration clears
