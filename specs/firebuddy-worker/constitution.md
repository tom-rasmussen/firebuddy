# FireBuddy constitution

The non-negotiable rules every spec, plan, task and line of code must follow.
If a requirement conflicts with this file, this file wins and the conflict goes in the decision log.

## 1. Purpose

FireBuddy explains what verified wildfire information means for one address.
It never creates or "detects" information on its own.

## 2. Safety rules (carried over from the Python build, PLAN.md section 2)

| Concern | Decided by | Rule |
|---|---|---|
| Whether to send an alert | Deterministic code | Never an LLM |
| Alert wording | Fixed templates | No LLM in the alert path |
| Readiness level ("should I leave?") | Deterministic rules (`assess`) | Wording may raise urgency, never lower it |
| Wind relative to a fire | Deterministic math | Explained, not computed by a model |
| Official orders and alerts | Quoted word for word, with sender and time | Never paraphrased |
| Evacuation routes | Not generated | Point to official sources |
| Safety claims | Never made | No "you're safe", "no need to leave", "you can stay" (only allowed inside a quoted official order) |

Every guidance reply ends with: "If you're in immediate danger, call 911. If you feel unsafe, leave. You don't need to wait for an order."

## 3. Honesty rules

- **Public information only.** No Watch Duty data, UI, branding, or anything seen while volunteering.
- **Independent concept.** Every page shows: "Independent concept, not affiliated with Watch Duty."
- **Simulated means labelled.** Every simulated fire, alert or shelter is marked SIMULATED where it appears.
- **No invented results.** Metrics, test results and resume numbers come only from things actually measured.

## 4. Quality gates

A phase is not done until:

1. Every acceptance criterion it touches (`spec.md`, AC-n) has at least one test named after it (`AC-n: …`).
2. The TypeScript engine matches the Python engine on the golden cases (parity tests).
3. `npm test` and `npm run typecheck` pass.
4. `STATUS.md` records what was built, what was verified, and anything blocked.

## 5. Scope discipline

Anything not in `spec.md` is out of scope. New ideas go under "Later" in `tasks.md`, not into the build.
