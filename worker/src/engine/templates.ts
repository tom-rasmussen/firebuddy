// Port of the alert and status templates in firebuddy/templates.py.
// Constitution section 2: alert wording comes only from these fixed templates.

import { compass16 } from "./geo";
import { fmtG, fmtThousands } from "./pyfmt";
import { pyStr } from "./pystr";
import type { Fire, OfficialAlert, WindData } from "./types";

export const DEFAULT_TIMEZONE = "America/Los_Angeles";
export const GROWTH_THRESHOLDS = [100, 1_000, 10_000, 100_000];
export const MAX_ALERT_CHARS = 480;

export const WIND_RELATION_PHRASES: Record<string, string> = {
  toward: "blowing from {fire} toward you",
  away: "blowing away from {fire}",
  crosswind: "crosswind to {fire}",
  light_variable: "light and variable",
};

export const FEEL_UNSAFE_LINE =
  "If you're in immediate danger, call 911. If you feel unsafe, leave. You don't need to wait for an order.";

/** "4:12 PM PDT" in the place's time zone. */
export function formatTime(iso: string | null | undefined, tzName?: string | null): string {
  if (!iso) return "time unknown";
  const date = new Date(iso);
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone: tzName || DEFAULT_TIMEZONE,
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZoneName: "short",
    }).formatToParts(date);
  } catch {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "UTC",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZoneName: "short",
    }).formatToParts(date);
  }
  const get = (t: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === t)?.value ?? "";
  const label = get("timeZoneName");
  const time = `${get("hour")}:${get("minute")} ${get("dayPeriod").toUpperCase()}`;
  return label ? `${time} ${label}` : time;
}

export function fireLine(fire: Fire, tzName?: string | null): string {
  const acres = fire.acres != null ? `${fmtG(fire.acres)} acres` : "size unknown";
  const contained = fire.percent_contained != null ? `${fmtG(fire.percent_contained)}% contained` : "containment unknown";
  return (
    `"${fire.name}," ~${fmtG(fire.distance_mi)} mi ${fire.direction}, ${acres}, ` +
    `${contained} (${fire.source}, updated ${formatTime(fire.updated, tzName)})`
  );
}

export function noOtherNwsAlertsNote(): string {
  return "No official NWS fire alerts for your location right now.";
}

export function newFireAlert(placeLabel: string, fire: Fire, otherAlertsNote: string, tzName?: string | null): string {
  return (
    `\u{1F525} New fire near ${placeLabel}: ${fireLine(fire, tzName)}. ` +
    `${otherAlertsNote} Reply with any question, e.g. "should I leave?"`
  );
}

export function growthAlert(placeLabel: string, fire: Fire, threshold: number, tzName?: string | null): string {
  return `\u{1F525} Growing fire near ${placeLabel}: ${fireLine(fire, tzName)} (crossed ${fmtThousands(threshold)} acres).`;
}

export function containmentAlert(placeLabel: string, fire: Fire, tzName?: string | null): string {
  return (
    `✅ ${fire.name} near ${placeLabel} is now 100% contained ` +
    `(${fire.source}, updated ${formatTime(fire.updated, tzName)}).`
  );
}

/** Official alert, quoted word for word (AC-3), truncated at 480 characters with a link. */
export function officialAlertText(placeLabel: string, alert: OfficialAlert, tzName?: string | null): string {
  const headline = alert.headline || "";
  const body = alert.instruction || alert.description || "";
  const lines = [`⚠️ ${alert.event} near ${placeLabel}: ${headline}`];
  if (body && body.trim() !== headline.trim()) lines.push(body);
  lines.push(`(${pyStr(alert.sender_name)}, sent ${formatTime(alert.sent, tzName)})`);
  let text = lines.join("\n");
  const chars = [...text];
  if (chars.length > MAX_ALERT_CHARS) {
    const link = "https://api.weather.gov/alerts/active";
    const keep = MAX_ALERT_CHARS - link.length - 5;
    text = `${chars.slice(0, keep).join("").trimEnd()}… ${link}`;
  }
  return text;
}

export function windLine(wind: WindData, tzName?: string | null): string {
  const directionDeg = wind.wind_from_deg;
  const speed = wind.wind_speed_mph;
  if (directionDeg == null || speed == null) return partialWindLine(wind, tzName);
  let speedBit = `from ${compass16(directionDeg)} at ${fmtG(speed)} mph`;
  if (wind.wind_gust_mph != null) speedBit += ` (gusts ${fmtG(wind.wind_gust_mph)})`;

  let relationBit = "";
  const relation = wind.relation_to_fire;
  const fireName = wind.relative_to_fire;
  const phrase = relation ? WIND_RELATION_PHRASES[relation] : undefined;
  if (phrase && (fireName || relation === "light_variable")) {
    relationBit = `, ${phrase.replace("{fire}", pyStr(fireName))}`;
  }

  const source = wind.station_id || "obs";
  const stale = wind.stale ? " -- stale" : "";
  return `Wind: ${speedBit}${relationBit} (${source} obs, ${formatTime(wind.obs_time, tzName)}${stale}).`;
}

function partialWindLine(wind: WindData, tzName?: string | null): string {
  const parts: string[] = [];
  if (wind.wind_gust_mph != null) {
    const source = wind.station_id || "obs";
    const stale = wind.stale ? " -- stale" : "";
    parts.push(
      `gusts ${fmtG(wind.wind_gust_mph)} mph, no steady reading (${source} obs, ${formatTime(wind.obs_time, tzName)}${stale})`,
    );
  }
  const forecast = (wind.forecast_hourly ?? []).find((p) => p.wind_speed);
  if (forecast) {
    const direction = forecast.wind_direction ? `${forecast.wind_direction} ` : "";
    parts.push(`forecast ${direction}${forecast.wind_speed} from ${formatTime(forecast.start_time, tzName)}`);
  }
  if (parts.length === 0) return "Wind: observation unavailable.";
  return `Wind: ${parts.join("; ")}.`;
}

export function statusUpdate(
  placeLabel: string,
  fires: Fire[],
  alerts: OfficialAlert[],
  wind: WindData | null = null,
  tzName?: string | null,
): string {
  const lines = [`Status check for ${placeLabel}:`];
  if (fires.length === 0 && alerts.length === 0) {
    lines.push("Nothing nearby right now.");
  } else {
    for (const f of fires) lines.push(`- ${fireLine(f, tzName)}`);
    for (const a of alerts) lines.push(`- ${a.event}: ${pyStr(a.headline)}`);
  }
  if (wind) lines.push(windLine(wind, tzName));
  return lines.join("\n");
}
