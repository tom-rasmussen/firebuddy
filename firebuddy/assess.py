from datetime import datetime

from firebuddy import geo

STALE_AFTER_HOURS = 2
LIGHT_WIND_MPH = 5
TOWARD_MAX_DEG = 45
CROSSWIND_MAX_DEG = 90

LEAVE_NOW_EVENTS = {"Fire Warning", "Evacuation Immediate"}
SHELTER_EVENT = "Shelter In Place Warning"
RED_FLAG_EVENT = "Red Flag Warning"

LEVEL_LEAVE_NOW = "LEAVE NOW"
LEVEL_SHELTER = "FOLLOW SHELTER ORDER"
LEVEL_GET_READY = "GET READY: LEAVE EARLY IF YOU NEED TIME"
LEVEL_BE_READY = "BE READY"
LEVEL_MONITOR = "MONITOR"

GUIDANCE_TEXT = {
    LEVEL_LEAVE_NOW: "Follow the order and leave now.",
    LEVEL_GET_READY: "Leave now if you have kids, pets, livestock, or mobility needs, or if you feel unsafe.",
    LEVEL_BE_READY: "Pack a go-bag, know your zone and two ways out.",
    LEVEL_MONITOR: "Nothing nearby right now. I'll text you if that changes.",
}

GET_READY_MAX_DISTANCE_MI = 5


def wind_relation(wind_from_deg: float | None, speed_mph: float | None, bearing_to_fire_deg: float) -> str:
    """toward / crosswind / away / light_variable / unknown, per section 5 wind math."""
    if wind_from_deg is None or speed_mph is None:
        return "unknown"
    if speed_mph < LIGHT_WIND_MPH:
        return "light_variable"
    d = geo.angular_diff(wind_from_deg, bearing_to_fire_deg)
    if d <= TOWARD_MAX_DEG:
        return "toward"
    if d <= CROSSWIND_MAX_DEG:
        return "crosswind"
    return "away"


def wind_is_stale(obs_time_iso: str | None, now: datetime) -> bool:
    if not obs_time_iso:
        return True
    obs_time = datetime.fromisoformat(obs_time_iso)
    age_hours = (now - obs_time).total_seconds() / 3600
    return age_hours > STALE_AFTER_HOURS


def wind_check(wind: dict, bearing_to_fire_deg: float | None, now: datetime) -> dict:
    """Pure composition of a wind_data() result into the shape `wind_check` tool returns.
    `bearing_to_fire_deg` is the exact bearing from place to the incident of interest, or
    None if there's no fire to relate the wind to."""
    relation = None
    if bearing_to_fire_deg is not None:
        relation = wind_relation(wind.get("wind_from_deg"), wind.get("wind_speed_mph"), bearing_to_fire_deg)
    return {
        "station_id": wind.get("station_id"),
        "station_distance_mi": wind.get("station_distance_mi"),
        "obs_time": wind.get("obs_time"),
        "stale": wind_is_stale(wind.get("obs_time"), now),
        "wind_from_deg": wind.get("wind_from_deg"),
        "wind_speed_mph": wind.get("wind_speed_mph"),
        "wind_gust_mph": wind.get("wind_gust_mph"),
        "relation_to_fire": relation,
        "forecast_hourly": wind.get("forecast_hourly", []),
        "caveat": "Local and terrain winds can differ, and embers can travel miles ahead of a fire.",
    }


def assess_situation(
    fires: list[dict],
    alerts: list[dict],
    wind_relation_to_nearest_fire: str | None = None,
    user_reports_evac_order: bool = False,
) -> dict:
    """Deterministic guidance level per section 5's `assess_situation` rules table.
    `fires` must already be filtered to the place's radius. `wind_relation_to_nearest_fire`
    is the output of `wind_relation()`/`wind_check()` for the nearest fire, if any."""
    events = {a.get("event") for a in alerts}
    nearest_fire = min(fires, key=lambda f: f["distance_mi"]) if fires else None
    has_leave_now_alert = bool(events & LEAVE_NOW_EVENTS)
    has_shelter_alert = SHELTER_EVENT in events
    has_red_flag = RED_FLAG_EVENT in events
    fire_within_5mi = nearest_fire is not None and nearest_fire["distance_mi"] <= GET_READY_MAX_DISTANCE_MI
    wind_toward = wind_relation_to_nearest_fire == "toward"

    facts: list[str] = []

    if has_leave_now_alert or user_reports_evac_order:
        level = LEVEL_LEAVE_NOW
        guidance = GUIDANCE_TEXT[level]
        if user_reports_evac_order:
            facts.append("User reported receiving an official evacuation order.")
        for a in alerts:
            if a.get("event") in LEAVE_NOW_EVENTS:
                facts.append(f"{a['event']}: {a.get('headline')}")
        return {"level": level, "guidance": guidance, "facts": facts}

    if has_shelter_alert:
        shelter_alert = next(a for a in alerts if a.get("event") == SHELTER_EVENT)
        level = LEVEL_SHELTER
        guidance = shelter_alert.get("instruction") or shelter_alert.get("description") or GUIDANCE_TEXT.get(
            level, "Follow the shelter-in-place order."
        )
        facts.append(f"{shelter_alert['event']}: {shelter_alert.get('headline')}")
        return {"level": level, "guidance": guidance, "facts": facts}

    if fire_within_5mi or (nearest_fire is not None and wind_toward) or (nearest_fire is not None and has_red_flag):
        level = LEVEL_GET_READY
        guidance = GUIDANCE_TEXT[level]
        if fire_within_5mi:
            facts.append(f"{nearest_fire['name']} is {nearest_fire['distance_mi']} mi away.")
        if wind_toward:
            facts.append("Wind is blowing from the fire toward you.")
        if has_red_flag:
            facts.append("Red Flag Warning is in effect.")
        return {"level": level, "guidance": guidance, "facts": facts}

    if nearest_fire is not None or (has_red_flag and nearest_fire is None):
        level = LEVEL_BE_READY
        guidance = GUIDANCE_TEXT[level]
        if nearest_fire is not None:
            facts.append(f"{nearest_fire['name']} is {nearest_fire['distance_mi']} mi away, wind not toward you.")
        if has_red_flag:
            facts.append("Red Flag Warning is in effect.")
        return {"level": level, "guidance": guidance, "facts": facts}

    return {"level": LEVEL_MONITOR, "guidance": GUIDANCE_TEXT[LEVEL_MONITOR], "facts": facts}
