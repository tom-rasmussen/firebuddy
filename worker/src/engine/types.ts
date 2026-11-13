// Shapes shared by the engine, scenario and API. Field names match the Python build.

export interface Fire {
  key: string;
  name: string;
  acres: number | null;
  percent_contained: number | null;
  distance_mi: number;
  direction: string;
  bearing_deg: number;
  discovered: string | null;
  updated: string | null;
  source: string;
}

export interface OfficialAlert {
  id: string;
  event: string;
  headline: string | null;
  description: string | null;
  instruction: string | null;
  sent: string | null;
  expires: string | null;
  sender_name: string | null;
  severity?: string | null;
  urgency?: string | null;
  area_desc?: string | null;
}

export interface ForecastPeriod {
  start_time: string | null;
  wind_speed: string | null;
  wind_direction: string | null;
}

export interface WindData {
  station_id?: string | null;
  station_distance_mi?: number | null;
  obs_time?: string | null;
  wind_from_deg?: number | null;
  wind_speed_mph?: number | null;
  wind_gust_mph?: number | null;
  forecast_hourly?: ForecastPeriod[];
  // Set when the wind is described relative to a fire (templates.wind_line).
  relation_to_fire?: WindRelation | null;
  relative_to_fire?: string | null;
  stale?: boolean;
}

export type WindRelation = "toward" | "crosswind" | "away" | "light_variable" | "unknown";

export interface Shelter {
  name: string;
  address: string;
  distance_mi: number;
  pets: string | null;
  ada: string | null;
  org: string | null;
  status: string | null;
}

export interface Assessment {
  level: string;
  guidance: string;
  facts: string[];
}
