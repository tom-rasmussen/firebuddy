// SIMULATED replay scenario: the "Morgan Fire" near Danville, CA.
// Invented for the demo. Every source label says "simulated" (constitution section 3, AC-10).

import { bearingDeg, compass16, haversineMi } from "../engine/geo";
import { pyRound } from "../engine/pyfmt";
import type { Fire, OfficialAlert, Shelter, WindData } from "../engine/types";

export const PLACE = { label: "Home", address: "Danville, CA (simulated)", lat: 37.8216, lon: -122.0001 };
export const TZ = "America/Los_Angeles";
export const RADIUS_MI = 15;

const FIRE_POINT = { lat: 37.8216, lon: -121.8353 }; // ~9 mi east
const SHELTER_POINT = { lat: 37.8277, lon: -121.9775 };

interface RawFire {
  key: string;
  name: string;
  acres: number;
  contained: number;
  discovered: string;
  updated: string;
}

interface RawStep {
  title: string;
  clock: string; // ISO time of this moment in the scenario
  baseline: string | null; // generic county-level alert, unbranded
  fires: RawFire[];
  alerts: OfficialAlert[];
  wind: { from: number; mph: number; gust: number | null; obs: string; forecast: { start: string; speed: string; dir: string }[] };
  shelterOpen: boolean;
}

const DAY1 = "2026-10-25";
const t = (hm: string, day = DAY1) => `${day}T${hm}:00-07:00`;

const fire = (acres: number, contained: number, updated: string): RawFire => ({
  key: "SIM-MORGAN",
  name: "Morgan Fire",
  acres,
  contained,
  discovered: t("15:52"),
  updated,
});

const RED_FLAG: OfficialAlert = {
  id: "sim-redflag-1",
  event: "Red Flag Warning",
  headline: "Red Flag Warning issued for Contra Costa County (simulated)",
  description:
    "East winds 15 to 25 mph with gusts up to 40 mph and relative humidity as low as 10 percent will produce extreme fire behavior.",
  instruction: "Avoid outdoor burning. Use extreme caution with anything that can spark a wildfire.",
  sent: t("16:20"),
  expires: t("20:00", "2026-10-26"),
  sender_name: "NWS San Francisco Bay Area (simulated)",
  severity: "Severe",
  urgency: "Expected",
  area_desc: "Contra Costa County",
};

const EVAC: OfficialAlert = {
  id: "sim-evac-1",
  event: "Evacuation Immediate",
  headline: "Evacuation order for eastern Danville zones due to the Morgan Fire (simulated)",
  description: "Law enforcement has ordered an immediate evacuation for zones east of the Danville town center.",
  instruction:
    "Leave now. Follow directions from law enforcement and use the routes they designate. Check your zone at protect.genasys.com.",
  sent: t("18:10"),
  expires: t("06:00", "2026-10-26"),
  sender_name: "Contra Costa County Sheriff via NWS (simulated)",
  severity: "Extreme",
  urgency: "Immediate",
  area_desc: "Eastern Danville",
};

const forecastEast = [
  { start: t("18:00"), speed: "15 to 20 mph", dir: "E" },
  { start: t("21:00"), speed: "10 mph", dir: "NE" },
];
const forecastEvening = [
  { start: t("19:00"), speed: "15 to 20 mph", dir: "E" },
  { start: t("22:00"), speed: "10 mph", dir: "NE" },
];
const forecastNight = [
  { start: t("20:00"), speed: "10 to 15 mph", dir: "NE" },
  { start: t("23:00"), speed: "5 to 10 mph", dir: "N" },
];

const STEPS: RawStep[] = [
  {
    title: "Quiet afternoon",
    clock: t("15:00"),
    baseline: null,
    fires: [],
    alerts: [],
    wind: { from: 270, mph: 8, gust: null, obs: t("14:50"), forecast: [{ start: t("16:00"), speed: "5 to 10 mph", dir: "W" }] },
    shelterOpen: false,
  },
  {
    title: "A fire starts 9 miles east",
    clock: t("16:00"),
    baseline: "Contra Costa County: New wildfire reported, Morgan Fire, approx. 40 acres. Open the app for details.",
    fires: [fire(40, 0, t("15:58"))],
    alerts: [],
    wind: { from: 270, mph: 8, gust: 12, obs: t("15:50"), forecast: [{ start: t("17:00"), speed: "10 to 15 mph", dir: "E" }] },
    shelterOpen: false,
  },
  {
    title: "Wind turns toward you; Red Flag Warning",
    clock: t("16:35"),
    baseline: "Contra Costa County: Red Flag Warning in effect until tomorrow 8 PM.",
    fires: [fire(85, 0, t("16:30"))],
    alerts: [RED_FLAG],
    wind: { from: 90, mph: 14, gust: 25, obs: t("16:30"), forecast: forecastEast },
    shelterOpen: false,
  },
  {
    title: "The fire grows past 100 acres",
    clock: t("17:45"),
    baseline: "Contra Costa County: Morgan Fire update, approx. 650 acres, 0% contained.",
    fires: [fire(650, 0, t("17:40"))],
    alerts: [RED_FLAG],
    wind: { from: 95, mph: 18, gust: 32, obs: t("17:40"), forecast: forecastEast },
    shelterOpen: false,
  },
  {
    title: "Evacuation order for your zone",
    clock: t("18:15"),
    baseline: "Contra Costa County: Evacuation orders issued for parts of Danville. Check your zone.",
    fires: [fire(900, 0, t("18:10"))],
    alerts: [RED_FLAG, EVAC],
    wind: { from: 95, mph: 18, gust: 35, obs: t("18:10"), forecast: forecastEvening },
    shelterOpen: false,
  },
  {
    title: "Shelter opens; fire passes 1,000 acres",
    clock: t("19:00"),
    baseline: "Contra Costa County: Evacuation shelter open. Morgan Fire approx. 1,400 acres, 5% contained.",
    fires: [fire(1400, 5, t("18:55"))],
    alerts: [RED_FLAG, EVAC],
    wind: { from: 80, mph: 15, gust: 28, obs: t("18:50"), forecast: forecastNight },
    shelterOpen: true,
  },
  {
    title: "Next morning: contained, order lifted",
    clock: t("10:00", "2026-10-26"),
    baseline: "Contra Costa County: Evacuation orders lifted. Morgan Fire 100% contained.",
    fires: [fire(2100, 100, t("09:45", "2026-10-26"))],
    alerts: [],
    wind: {
      from: 250,
      mph: 4,
      gust: null,
      obs: t("09:50", "2026-10-26"),
      forecast: [{ start: t("11:00", "2026-10-26"), speed: "5 mph", dir: "W" }],
    },
    shelterOpen: false,
  },
];

export const STEP_COUNT = STEPS.length;

export interface WorldState {
  step: number;
  title: string;
  clock: string;
  baseline: string | null;
  fires: Fire[];
  alerts: OfficialAlert[];
  wind: WindData;
  shelters: Shelter[];
}

function toFire(raw: RawFire): Fire {
  const d = haversineMi(PLACE.lat, PLACE.lon, FIRE_POINT.lat, FIRE_POINT.lon);
  const b = bearingDeg(PLACE.lat, PLACE.lon, FIRE_POINT.lat, FIRE_POINT.lon);
  return {
    key: raw.key,
    name: raw.name,
    acres: raw.acres,
    percent_contained: raw.contained,
    distance_mi: pyRound(d, 1),
    direction: compass16(b),
    bearing_deg: pyRound(b, 1),
    discovered: raw.discovered,
    updated: raw.updated,
    source: "simulated NIFC",
  };
}

function shelter(): Shelter {
  return {
    name: "Monte Vista HS Gym",
    address: "3131 Stone Valley Rd, Danville, CA, 94526",
    distance_mi: pyRound(haversineMi(PLACE.lat, PLACE.lon, SHELTER_POINT.lat, SHELTER_POINT.lon), 1),
    pets: "Y",
    ada: "Y",
    org: "American Red Cross (simulated)",
    status: "OPEN",
  };
}

export function stateAt(step: number): WorldState {
  const raw = STEPS[step];
  if (!raw) throw new RangeError(`step must be 0..${STEP_COUNT - 1}`);
  return {
    step,
    title: raw.title,
    clock: raw.clock,
    baseline: raw.baseline,
    fires: raw.fires.map(toFire),
    alerts: raw.alerts,
    wind: {
      station_id: "simulated KCCR",
      station_distance_mi: 6.4,
      obs_time: raw.wind.obs,
      wind_from_deg: raw.wind.from,
      wind_speed_mph: raw.wind.mph,
      wind_gust_mph: raw.wind.gust,
      forecast_hourly: raw.wind.forecast.map((f) => ({ start_time: f.start, wind_speed: f.speed, wind_direction: f.dir })),
    },
    shelters: raw.shelterOpen ? [shelter()] : [],
  };
}
