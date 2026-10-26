from datetime import datetime

GROWTH_THRESHOLDS = [100, 1_000, 10_000, 100_000]

FEEL_UNSAFE_LINE = (
    "If you're in immediate danger, call 911. If you feel unsafe, leave. "
    "You don't need to wait for an order."
)

ONBOARDING_GREETING = (
    "I'm FireBuddy. I watch for wildfires near places you care about and you can text me "
    "questions anytime. What address or town should I watch? "
    "(Reply STOP to opt out. I supplement, not replace, official alerts.)"
)


def format_time(iso_str: str | None) -> str:
    if not iso_str:
        return "time unknown"
    dt = datetime.fromisoformat(iso_str)
    hour = dt.strftime("%I").lstrip("0") or "0"
    minute = dt.strftime("%M")
    ampm = dt.strftime("%p")
    offset = dt.strftime("%z")
    if offset:
        offset_fmt = f"UTC{offset[:3]}:{offset[3:]}" if offset != "+0000" else "UTC"
    else:
        offset_fmt = ""
    return f"{hour}:{minute} {ampm} ({offset_fmt})" if offset_fmt else f"{hour}:{minute} {ampm}"


def _fire_line(fire: dict) -> str:
    acres = fire.get("acres")
    acres_str = f"{acres:g} acres" if acres is not None else "size unknown"
    contained = fire.get("percent_contained")
    contained_str = f"{contained:g}% contained" if contained is not None else "containment unknown"
    return (
        f'"{fire["name"]}," ~{fire["distance_mi"]:g} mi {fire["direction"]}, {acres_str}, '
        f'{contained_str} ({fire["source"]}, updated {format_time(fire.get("updated"))})'
    )


def onboarding_confirmed(label: str, address: str, radius_mi: float, fires: list[dict]) -> str:
    if fires:
        fire_bit = f"{len(fires)} active wildfire(s) within {radius_mi:g} mi right now."
    else:
        fire_bit = f"No active wildfires within {radius_mi:g} mi right now."
    return f"Watching {address} ({radius_mi:g} mi radius). {fire_bit} I'll text you if that changes."


def new_fire_alert(place_label: str, fire: dict, other_alerts_note: str) -> str:
    return (
        f"\U0001f525 New fire near {place_label}: {_fire_line(fire)}. "
        f'{other_alerts_note} Reply with any question, e.g. "should I leave?"'
    )


def growth_alert(place_label: str, fire: dict, threshold: int) -> str:
    return (
        f"\U0001f525 Growing fire near {place_label}: {_fire_line(fire)} "
        f"(crossed {threshold:,} acres)."
    )


def containment_alert(place_label: str, fire: dict) -> str:
    return (
        f"✅ {fire['name']} near {place_label} is now 100% contained "
        f"({fire['source']}, updated {format_time(fire.get('updated'))})."
    )


MAX_ALERT_CHARS = 480


def official_alert_text(place_label: str, alert: dict) -> str:
    body = alert.get("instruction") or alert.get("description") or ""
    text = (
        f"⚠️ {alert['event']} near {place_label}: {alert['headline']}\n"
        f"{body}\n"
        f"({alert['sender_name']}, sent {format_time(alert.get('sent'))})"
    )
    if len(text) > MAX_ALERT_CHARS:
        link = "https://api.weather.gov/alerts/active"
        keep = MAX_ALERT_CHARS - len(link) - 5
        text = text[:keep].rstrip() + "… " + link
    return text


def no_other_nws_alerts_note() -> str:
    return "No official NWS fire alerts for your location right now."


def status_update(place_label: str, fires: list[dict], alerts: list[dict]) -> str:
    if not fires and not alerts:
        return f"Status check for {place_label}: nothing nearby right now."
    lines = [f"Status check for {place_label}:"]
    for f in fires:
        lines.append(f"- {_fire_line(f)}")
    for a in alerts:
        lines.append(f"- {a['event']}: {a['headline']}")
    return "\n".join(lines)
