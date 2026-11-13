// Port of firebuddy/assess.py: deterministic wind math and readiness levels.
// Constitution section 2: these decisions are never made by an LLM.

import { angularDiff } from "./geo";
import { pyStr } from "./pystr";
import type { Assessment, Fire, OfficialAlert, WindData, WindRelation } from "./types";

export const STALE_AFTER_HOURS = 2;
export const LIGHT_WIND_MPH = 5;
export const TOWARD_MAX_DEG = 45;
export const CROSSWIND_MAX_DEG = 90;

export const LEAVE_NOW_EVENTS = new Set(["Fire Warning", "Evacuation Immediate"]);
export const SHELTER_EVENT = "Shelter In Place Warning";
export const RED_FLAG_EVENT = "Red Flag Warning";

export const LEVEL_LEAVE_NOW = "LEAVE NOW";
export const LEVEL_SHELTER = "FOLLOW SHELTER ORDER";
export const LEVEL_GET_READY = "GET READY: LEAVE EARLY IF YOU NEED TIME";
export const LEVEL_BE_READY = "BE READY";
export const LEVEL_MONITOR = "MONITOR";

export const GUIDANCE_TEXT: Record<string, string> = {
  [LEVEL_LEAVE_NOW]: "Follow the order and leave now.",
  [LEVEL_GET_READY]: "Leave now if you have kids, pets, livestock, or mobility needs, or if you feel unsafe.",
  [LEVEL_BE_READY]: "Pack a go-bag, know your zone and two ways out.",
  [LEVEL_MONITOR]: "Nothing nearby right now. I'll text you if that changes.",
};

export const GET_READY_MAX_DISTANCE_MI = 5;

/** Ordered from least to most urgent, for "never de-escalate" checks. */
export const LEVEL_ORDER = [LEVEL_MONITOR, LEVEL_BE_READY, LEVEL_GET_READY, LEVEL_SHELTER, LEVEL_LEAVE_NOW];

export function windRelation(
  windFromDeg: number | null | undefined,
  speedMph: number | null | undefined,
  bearingToFireDeg: number,
): WindRelation {
  if (windFromDeg == null || speedMph == null) return "unknown";
  if (speedMph < LIGHT_WIND_MPH) return "light_variable";
  const d = angularDiff(windFromDeg, bearingToFireDeg);
  if (d <= TOWARD_MAX_DEG) return "toward";
  if (d <= CROSSWIND_MAX_DEG) return "crosswind";
  return "away";
}

export function windIsStale(obsTimeIso: string | null | undefined, now: Date): boolean {
  if (!obsTimeIso) return true;
  const ageHours = (now.getTime() - Date.parse(obsTimeIso)) / 3_600_000;
  return ageHours > STALE_AFTER_HOURS;
}

export interface WindCheck {
  station_id: string | null;
  station_distance_mi: number | null;
  obs_time: string | null;
  stale: boolean;
  wind_from_deg: number | null;
  wind_speed_mph: number | null;
  wind_gust_mph: number | null;
  relation_to_fire: WindRelation | null;
  forecast_hourly: WindData["forecast_hourly"];
  caveat: string;
}

export function windCheck(wind: WindData, bearingToFireDeg: number | null, now: Date): WindCheck {
  const relation =
    bearingToFireDeg != null ? windRelation(wind.wind_from_deg, wind.wind_speed_mph, bearingToFireDeg) : null;
  return {
    station_id: wind.station_id ?? null,
    station_distance_mi: wind.station_distance_mi ?? null,
    obs_time: wind.obs_time ?? null,
    stale: windIsStale(wind.obs_time, now),
    wind_from_deg: wind.wind_from_deg ?? null,
    wind_speed_mph: wind.wind_speed_mph ?? null,
    wind_gust_mph: wind.wind_gust_mph ?? null,
    relation_to_fire: relation,
    forecast_hourly: wind.forecast_hourly ?? [],
    caveat: "Local and terrain winds can differ, and embers can travel miles ahead of a fire.",
  };
}

export function assessSituation(
  fires: Fire[],
  alerts: OfficialAlert[],
  windRelationToNearestFire: WindRelation | null = null,
  userReportsEvacOrder = false,
): Assessment {
  const events = new Set(alerts.map((a) => a.event));
  // Python's min() keeps the first of equal values.
  const nearest = fires.reduce<Fire | null>((best, f) => (best === null || f.distance_mi < best.distance_mi ? f : best), null);
  const hasLeaveNow = [...events].some((e) => LEAVE_NOW_EVENTS.has(e));
  const hasShelter = events.has(SHELTER_EVENT);
  const hasRedFlag = events.has(RED_FLAG_EVENT);
  const within5 = nearest !== null && nearest.distance_mi <= GET_READY_MAX_DISTANCE_MI;
  const windToward = windRelationToNearestFire === "toward";

  const facts: string[] = [];

  if (hasLeaveNow || userReportsEvacOrder) {
    if (userReportsEvacOrder) facts.push("User reported receiving an official evacuation order.");
    for (const a of alerts) {
      if (LEAVE_NOW_EVENTS.has(a.event)) facts.push(`${a.event}: ${pyStr(a.headline)}`);
    }
    return { level: LEVEL_LEAVE_NOW, guidance: GUIDANCE_TEXT[LEVEL_LEAVE_NOW] as string, facts };
  }

  if (hasShelter) {
    const s = alerts.find((a) => a.event === SHELTER_EVENT) as OfficialAlert;
    const guidance = s.instruction || s.description || GUIDANCE_TEXT[LEVEL_SHELTER] || "Follow the shelter-in-place order.";
    facts.push(`${s.event}: ${pyStr(s.headline)}`);
    return { level: LEVEL_SHELTER, guidance, facts };
  }

  if (within5 || (nearest !== null && windToward) || (nearest !== null && hasRedFlag)) {
    if (within5 && nearest) facts.push(`${nearest.name} is ${pyStr(nearest.distance_mi)} mi away.`);
    if (windToward) facts.push("Wind is blowing from the fire toward you.");
    if (hasRedFlag) facts.push("Red Flag Warning is in effect.");
    return { level: LEVEL_GET_READY, guidance: GUIDANCE_TEXT[LEVEL_GET_READY] as string, facts };
  }

  if (nearest !== null || hasRedFlag) {
    if (nearest !== null) facts.push(`${nearest.name} is ${pyStr(nearest.distance_mi)} mi away, wind not toward you.`);
    if (hasRedFlag) facts.push("Red Flag Warning is in effect.");
    return { level: LEVEL_BE_READY, guidance: GUIDANCE_TEXT[LEVEL_BE_READY] as string, facts };
  }

  return { level: LEVEL_MONITOR, guidance: GUIDANCE_TEXT[LEVEL_MONITOR] as string, facts };
}
