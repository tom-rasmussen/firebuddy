from datetime import datetime
from zoneinfo import ZoneInfo

from firebuddy import geo
from firebuddy.sources.nws import DEFAULT_TIMEZONE

GROWTH_THRESHOLDS = [100, 1_000, 10_000, 100_000]

WIND_RELATION_PHRASES = {
    "toward": "blowing from {fire} toward you",
    "away": "blowing away from {fire}",
    "crosswind": "crosswind to {fire}",
    "light_variable": "light and variable",
}

FEEL_UNSAFE_LINE = (
    "If you're in immediate danger, call 911. If you feel unsafe, leave. "
    "You don't need to wait for an order."
)

ONBOARDING_GREETING = (
    "I'm FireBuddy. I watch for wildfires near places you care about and you can text me "
    "questions anytime. What address or town should I watch? "
    "(Reply STOP to opt out. I supplement, not replace, official alerts.)"
)

GEOCODE_RETRY_TEXT = "I couldn't find '{address}'. Try a more specific address, or the nearest town and state."

STOPPED_TEXT = "You're opted out. I won't text you anymore. Reply START to resume."
STARTED_TEXT = "You're back in. I'll text you if anything changes near your places."

NO_PLACES_TEXT = "You're not watching any places yet. Text ADD <address> to add one."

AGENT_UNAVAILABLE_TEXT = (
    "I can't answer open-ended questions right now. Try ADD <address>, LIST, REMOVE <n>, "
    "RADIUS <mi> [place n], STATUS, STOP, START, or HELP."
)

HELP_TEXT = (
    "Commands:\n"
    "ADD <address> - watch a new place\n"
    "LIST - show your watched places\n"
    "REMOVE <n> - stop watching place n\n"
    "RADIUS <mi> [place n] - change watch radius\n"
    "STATUS - current fires/alerts for your places\n"
    "STOP - opt out\n"
    "START - opt back in\n"
    "HELP - this message\n"
    "Anything else (e.g. \"should I leave?\") goes to FireBuddy."
)


def format_time(iso_str: str | None, tz_name: str | None = None) -> str:
    """Format a timestamp in the place's local timezone (default DEFAULT_TIMEZONE),
    e.g. "11:48 PM PDT". Falls back to a UTC-offset label if the zone can't be
    resolved."""
    if not iso_str:
        return "time unknown"
    dt = datetime.fromisoformat(iso_str)
    try:
        dt = dt.astimezone(ZoneInfo(tz_name or DEFAULT_TIMEZONE))
        tz_label = dt.strftime("%Z")
    except Exception:
        offset = dt.strftime("%z")
        tz_label = f"UTC{offset[:3]}:{offset[3:]}" if offset and offset != "+0000" else "UTC"
    hour = dt.strftime("%I").lstrip("0") or "0"
    minute = dt.strftime("%M")
    ampm = dt.strftime("%p")
    return f"{hour}:{minute} {ampm} {tz_label}" if tz_label else f"{hour}:{minute} {ampm}"


def _fire_line(fire: dict, tz_name: str | None = None) -> str:
    acres = fire.get("acres")
    acres_str = f"{acres:g} acres" if acres is not None else "size unknown"
    contained = fire.get("percent_contained")
    contained_str = f"{contained:g}% contained" if contained is not None else "containment unknown"
    return (
        f'"{fire["name"]}," ~{fire["distance_mi"]:g} mi {fire["direction"]}, {acres_str}, '
        f'{contained_str} ({fire["source"]}, updated {format_time(fire.get("updated"), tz_name)})'
    )


def onboarding_confirmed(label: str, address: str, radius_mi: float, fires: list[dict]) -> str:
    if fires:
        fire_bit = f"{len(fires)} active wildfire(s) within {radius_mi:g} mi right now."
    else:
        fire_bit = f"No active wildfires within {radius_mi:g} mi right now."
    return f"Watching {address} ({radius_mi:g} mi radius). {fire_bit} I'll text you if that changes."


def new_fire_alert(place_label: str, fire: dict, other_alerts_note: str, tz_name: str | None = None) -> str:
    return (
        f"\U0001f525 New fire near {place_label}: {_fire_line(fire, tz_name)}. "
        f'{other_alerts_note} Reply with any question, e.g. "should I leave?"'
    )


def growth_alert(place_label: str, fire: dict, threshold: int, tz_name: str | None = None) -> str:
    return (
        f"\U0001f525 Growing fire near {place_label}: {_fire_line(fire, tz_name)} "
        f"(crossed {threshold:,} acres)."
    )


def containment_alert(place_label: str, fire: dict, tz_name: str | None = None) -> str:
    return (
        f"✅ {fire['name']} near {place_label} is now 100% contained "
        f"({fire['source']}, updated {format_time(fire.get('updated'), tz_name)})."
    )


MAX_ALERT_CHARS = 480


def official_alert_text(place_label: str, alert: dict, tz_name: str | None = None) -> str:
    headline = alert.get("headline") or ""
    body = alert.get("instruction") or alert.get("description") or ""
    lines = [f"⚠️ {alert['event']} near {place_label}: {headline}"]
    if body and body.strip() != headline.strip():
        lines.append(body)
    lines.append(f"({alert['sender_name']}, sent {format_time(alert.get('sent'), tz_name)})")
    text = "\n".join(lines)
    if len(text) > MAX_ALERT_CHARS:
        link = "https://api.weather.gov/alerts/active"
        keep = MAX_ALERT_CHARS - len(link) - 5
        text = text[:keep].rstrip() + "… " + link
    return text


def no_other_nws_alerts_note() -> str:
    return "No official NWS fire alerts for your location right now."


def wind_line(wind: dict, tz_name: str | None = None) -> str:
    direction_deg = wind.get("wind_from_deg")
    speed = wind.get("wind_speed_mph")
    if direction_deg is None or speed is None:
        return "Wind: observation unavailable."
    direction = geo.compass_16(direction_deg)
    speed_bit = f"from {direction} at {speed:g} mph"
    gust = wind.get("wind_gust_mph")
    if gust is not None:
        speed_bit += f" (gusts {gust:g})"

    relation_bit = ""
    relation = wind.get("relation_to_fire")
    fire_name = wind.get("relative_to_fire")
    phrase_template = WIND_RELATION_PHRASES.get(relation)
    if phrase_template and (fire_name or relation == "light_variable"):
        relation_bit = f", {phrase_template.format(fire=fire_name)}"

    source = wind.get("station_id") or "obs"
    time_bit = format_time(wind.get("obs_time"), tz_name)
    stale_bit = " -- stale" if wind.get("stale") else ""
    return f"Wind: {speed_bit}{relation_bit} ({source} obs, {time_bit}{stale_bit})."


def status_update(
    place_label: str,
    fires: list[dict],
    alerts: list[dict],
    wind: dict | None = None,
    tz_name: str | None = None,
) -> str:
    lines = [f"Status check for {place_label}:"]
    if not fires and not alerts:
        lines.append("Nothing nearby right now.")
    else:
        for f in fires:
            lines.append(f"- {_fire_line(f, tz_name)}")
        for a in alerts:
            lines.append(f"- {a['event']}: {a['headline']}")
    if wind:
        lines.append(wind_line(wind, tz_name))
    return "\n".join(lines)
