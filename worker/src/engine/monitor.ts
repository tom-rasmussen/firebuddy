// Port of the trigger logic in firebuddy/monitor.py, run over the replay timeline.
// Alerts are deduped by event key: each event alerts exactly once (AC-1, AC-2, AC-3).

import { assessSituation, windCheck } from "./assess";
import {
  GROWTH_THRESHOLDS,
  containmentAlert,
  growthAlert,
  newFireAlert,
  noOtherNwsAlertsNote,
  officialAlertText,
} from "./templates";
import type { Assessment, Fire, WindData } from "./types";
import { PLACE, STEP_COUNT, TZ, stateAt, type WorldState } from "../scenario/morgan";

/** NWS events that trigger a proactive alert (PLAN.md section 4). */
export const WATCHED_EVENTS = new Set([
  "Fire Warning",
  "Evacuation Immediate",
  "Red Flag Warning",
  "Fire Weather Watch",
  "Shelter In Place Warning",
  "Civil Emergency Message",
  "Local Area Emergency",
]);

export type AlertKind = "new_fire" | "growth" | "containment" | "official";

export interface ProactiveAlert {
  key: string;
  kind: AlertKind;
  text: string;
}

function nearest(fires: Fire[]): Fire | null {
  return fires.reduce<Fire | null>((best, f) => (best === null || f.distance_mi < best.distance_mi ? f : best), null);
}

/** Wind described relative to the nearest fire, as agent.wind_for_place does in the Python build. */
export function windForState(state: WorldState): WindData {
  const fire = nearest(state.fires);
  const check = windCheck(state.wind, fire ? fire.bearing_deg : null, new Date(state.clock));
  return {
    ...state.wind,
    stale: check.stale,
    relation_to_fire: check.relation_to_fire,
    relative_to_fire: fire ? fire.name : null,
  };
}

export function assessState(state: WorldState): Assessment {
  const wind = windForState(state);
  return assessSituation(state.fires, state.alerts, wind.relation_to_fire ?? null);
}

/** Alerts sent at each step, computed by replaying the timeline from step 0 with dedupe. */
function replay(): ProactiveAlert[][] {
  const sent = new Set<string>();
  const crossed = new Map<string, Set<number>>();
  const out: ProactiveAlert[][] = [];
  for (let n = 0; n < STEP_COUNT; n++) {
    const state = stateAt(n);
    const step: ProactiveAlert[] = [];
    const send = (key: string, kind: AlertKind, text: string) => {
      if (sent.has(key)) return;
      sent.add(key);
      step.push({ key, kind, text });
    };
    const watched = state.alerts.filter((a) => WATCHED_EVENTS.has(a.event));

    for (const fire of state.fires) {
      const acres = fire.acres ?? 0;
      const reached = GROWTH_THRESHOLDS.filter((th) => acres >= th);
      const isNew = !sent.has(`new:${fire.key}`);
      if (isNew) {
        // A fire first seen past a threshold doesn't also get a growth alert (STATUS.md, Phase 2).
        crossed.set(fire.key, new Set(reached));
        // Deviation from monitor.py, which always says "no official alerts" here even when one exists.
        const note = watched.length === 0 ? noOtherNwsAlertsNote() : "Official alerts are in effect for your location; see below.";
        send(`new:${fire.key}`, "new_fire", newFireAlert(PLACE.label, fire, note, TZ));
        continue;
      }
      const done = crossed.get(fire.key) ?? new Set<number>();
      for (const th of reached) {
        if (!done.has(th)) {
          done.add(th);
          send(`growth:${fire.key}:${th}`, "growth", growthAlert(PLACE.label, fire, th, TZ));
        }
      }
      if (fire.percent_contained === 100) {
        send(`contain:${fire.key}`, "containment", containmentAlert(PLACE.label, fire, TZ));
      }
    }
    for (const alert of watched) {
      send(`nws:${alert.id}`, "official", officialAlertText(PLACE.label, alert, TZ));
    }
    out.push(step);
  }
  return out;
}

const REPLAY = replay();

export function alertsAt(step: number): ProactiveAlert[] {
  const alerts = REPLAY[step];
  if (!alerts) throw new RangeError(`step must be 0..${STEP_COUNT - 1}`);
  return alerts;
}
