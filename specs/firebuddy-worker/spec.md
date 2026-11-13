# FireBuddy web demo: spec

Owner: Tom Rasmussen · Status: draft for review · Rules: [constitution.md](constitution.md)

## Problem

County-level fire alerts tell people that a fire exists, not what it means for their home.
To decide what to do, a resident still has to read a map, judge distance and wind, and work out a readiness level while stressed.

**Job to be done:** When a fire alert hits my county, help me decide whether my home needs action, so I don't have to read a map under stress.

## Hypothesis

If an assistant turns verified alerts into an answer for one address (distance, wind, readiness level, next step), people will reach a correct readiness decision faster than with a county-level alert alone.

## Users

| Persona | Situation | What they need |
|---|---|---|
| **Resident** (primary) | Lives in a wildfire-prone area, already gets county alerts | "Does this fire matter for my house, and what should I do now?" |
| **Remote caretaker** | Watching a parent's or relative's home from elsewhere | The same answer for a place they aren't at |
| **Needs-more-time household** | Kids, pets, livestock, or mobility limits | To know early when to leave before an order |

## User stories and acceptance criteria

**S1. Proactive alert.** As a resident, I get one alert when something near my address changes, so I don't have to keep checking.
- **AC-1** A new fire within the watch radius produces exactly one alert, with distance, direction, size, containment, source and time.
- **AC-2** A fire crossing 100 / 1,000 / 10,000 / 100,000 acres produces one alert per threshold; full containment produces one closure alert. Nothing repeats across later steps.
- **AC-3** Official alerts (for example a Red Flag Warning or evacuation order) are shown word for word with sender and sent time.

**S2. "Should I leave?"** As a resident, I get a straight readiness answer for my address.
- **AC-4** The readiness level always equals the deterministic rules' output for the current state (LEAVE NOW, FOLLOW SHELTER ORDER, GET READY, BE READY, MONITOR).
- **AC-5** An evacuation order or Fire Warning always produces LEAVE NOW. A shelter-in-place order never tells the user to leave and quotes the order.
- **AC-6** The answer lists the facts behind the level and ends with the 911 / "if you feel unsafe, leave" line.

**S3. Wind.** As a resident, I can ask whether the wind is blowing the fire my way.
- **AC-7** The answer says toward / crosswind / away / light and variable, gives the observation source and time, flags readings over 2 hours old, and includes the terrain and ember caveat.

**S4. Shelter.** As a resident, I can ask where to go.
- **AC-8** Open shelters are listed nearest first with distance, pets and accessibility, plus "confirm with your county". If none are open, it says so and points to county OES and 211.

**S5. Trust.** As anyone, I can tell what's official, what's simulated, and who decided each reply.
- **AC-9** No reply contains a safety claim or a generated route (constitution section 2).
- **AC-10** The disclaimer and SIMULATED labels are visible on every screen.
- **AC-11** Each reply shows which component decided it (rules or template) and the readiness level.

**S6. Compare with today.** As a reviewer, I can see the county-level baseline next to FireBuddy for the same moment.
- **AC-12** Each scenario step shows a generic, unbranded county-level alert next to FireBuddy's version.

**S7. Measure it (test mode).** As the PM running the user test, I can time decisions in each condition.
- **AC-13** `?mode=baseline` shows only the county alert; `?mode=firebuddy` shows the full experience.
- **AC-14** When a participant picks a decision, the demo records the choice, the seconds since the first alert, and whether it matches the correct level. Results can be copied; nothing is stored on a server.

**S8. Safe to share publicly.**
- **AC-15** `/api/*` is rate-limited per IP; over the limit returns HTTP 429 with a plain-language message.
- **AC-16** The demo is usable at 375 px wide (phone).

## Success metrics

| Type | Metric | How measured | Target |
|---|---|---|---|
| Primary | Median seconds from first alert to a correct readiness decision | Test mode, same participants, baseline then FireBuddy | Lower with FireBuddy |
| Quality | Share of decisions that match the correct level | Test mode | Higher with FireBuddy |
| Guardrail | Safety claims or generated routes in any reply | AC-9 tests | 0 |
| Guardrail | Alerts per incident step | AC-2 tests | 1 per event, no repeats |

## Non-goals

SMS delivery, live LLM answers, live fire data, accounts or saved places, floods and other hazards.
