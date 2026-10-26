import re

from firebuddy import agent, config, db, templates
from firebuddy.sources import fires as fires_source
from firebuddy.sources import geocode
from firebuddy.sources import nws as nws_source

ADD_RE = re.compile(r"^ADD\s+(.+)$", re.IGNORECASE)
LIST_RE = re.compile(r"^LIST$", re.IGNORECASE)
REMOVE_RE = re.compile(r"^REMOVE\s+(\d+)$", re.IGNORECASE)
RADIUS_RE = re.compile(r"^RADIUS\s+(\d+(?:\.\d+)?)(?:\s+(?:PLACE\s+)?(\d+))?$", re.IGNORECASE)
STATUS_RE = re.compile(r"^STATUS$", re.IGNORECASE)
STOP_RE = re.compile(r"^STOP$", re.IGNORECASE)
START_RE = re.compile(r"^START$", re.IGNORECASE)
HELP_RE = re.compile(r"^HELP$", re.IGNORECASE)


def parse_command(text: str):
    text = text.strip()
    if m := ADD_RE.match(text):
        return ("ADD", m.group(1).strip())
    if LIST_RE.match(text):
        return ("LIST", None)
    if m := REMOVE_RE.match(text):
        return ("REMOVE", int(m.group(1)))
    if m := RADIUS_RE.match(text):
        place_n = int(m.group(2)) if m.group(2) else 1
        return ("RADIUS", (float(m.group(1)), place_n))
    if STATUS_RE.match(text):
        return ("STATUS", None)
    if STOP_RE.match(text):
        return ("STOP", None)
    if START_RE.match(text):
        return ("START", None)
    if HELP_RE.match(text):
        return ("HELP", None)
    return None


def _default_label(conn, user_id: int) -> str:
    existing = db.list_places(conn, user_id)
    return "Home" if not existing else f"Place {len(existing) + 1}"


def _handle_add(conn, user, address: str) -> str:
    try:
        loc = geocode.geocode(address)
    except geocode.GeocodeError:
        return templates.GEOCODE_RETRY_TEXT.format(address=address)
    label = _default_label(conn, user["id"])
    place = db.add_place(conn, user["id"], label, loc["matched_address"], loc["lat"], loc["lon"], 15)
    return f'Added "{place["label"]}": {place["address"]} ({place["radius_mi"]:g} mi radius).'


def _handle_list(conn, user) -> str:
    places = db.list_places(conn, user["id"])
    if not places:
        return templates.NO_PLACES_TEXT
    lines = [f"{i + 1}. {p['label']}: {p['address']} ({p['radius_mi']:g} mi)" for i, p in enumerate(places)]
    return "\n".join(lines)


def _handle_remove(conn, user, n: int) -> str:
    places = db.list_places(conn, user["id"])
    idx = n - 1
    if idx < 0 or idx >= len(places):
        return f"No place #{n}. Text LIST to see your places."
    place = places[idx]
    db.remove_place(conn, place["id"])
    return f'Removed "{place["label"]}".'


def _handle_radius(conn, user, miles: float, place_n: int) -> str:
    places = db.list_places(conn, user["id"])
    idx = place_n - 1
    if idx < 0 or idx >= len(places):
        return f"No place #{place_n}. Text LIST to see your places."
    place = places[idx]
    radius = max(1, min(50, miles))
    db.set_radius(conn, place["id"], radius)
    return f'Set "{place["label"]}" radius to {radius:g} mi.'


def _handle_status(conn, user) -> str:
    places = db.list_places(conn, user["id"])
    if not places:
        return templates.NO_PLACES_TEXT
    parts = []
    for p in places:
        fires = fires_source.fires_near(p["lat"], p["lon"], p["radius_mi"])
        alerts = nws_source.official_alerts(p["lat"], p["lon"])
        wind = agent.wind_for_place(p)
        tz_name = nws_source.get_timezone(p["lat"], p["lon"])
        parts.append(templates.status_update(p["label"], fires, alerts, wind, tz_name))
    return "\n\n".join(parts)


def handle_command(conn, user, cmd) -> str:
    name, arg = cmd
    if name == "STOP":
        db.set_user_status(conn, user["id"], "stopped")
        return templates.STOPPED_TEXT
    if name == "START":
        db.set_user_status(conn, user["id"], "active")
        return templates.STARTED_TEXT
    if name == "HELP":
        return templates.HELP_TEXT
    if name == "LIST":
        return _handle_list(conn, user)
    if name == "ADD":
        return _handle_add(conn, user, arg)
    if name == "REMOVE":
        return _handle_remove(conn, user, arg)
    if name == "RADIUS":
        miles, place_n = arg
        return _handle_radius(conn, user, miles, place_n)
    if name == "STATUS":
        return _handle_status(conn, user)
    raise AssertionError(f"unhandled command: {name}")


def _handle_onboarding_address(conn, user, address: str) -> str:
    try:
        loc = geocode.geocode(address)
    except geocode.GeocodeError:
        return templates.GEOCODE_RETRY_TEXT.format(address=address)
    place = db.add_place(conn, user["id"], "Home", loc["matched_address"], loc["lat"], loc["lon"], 15)
    db.set_user_state(conn, user["id"], None)
    fires = fires_source.fires_near(place["lat"], place["lon"], place["radius_mi"])
    return templates.onboarding_confirmed(place["label"], place["address"], place["radius_mi"], fires)


def route_message(conn, phone: str, text: str, llm_client=None) -> str | None:
    """Route one inbound SMS. Returns the reply text, or None if nothing should be sent."""
    user = db.get_or_create_user(conn, phone)
    stripped = text.strip()

    cmd = parse_command(stripped)
    if cmd is not None:
        reply = handle_command(conn, user, cmd)
        db.log_message(conn, user["id"], "in", text)
        db.log_message(conn, user["id"], "out", reply)
        return reply

    if user["status"] == "stopped":
        db.log_message(conn, user["id"], "in", text)
        return None

    if user["state"] == "awaiting_address":
        reply = _handle_onboarding_address(conn, user, stripped)
        db.log_message(conn, user["id"], "in", text)
        db.log_message(conn, user["id"], "out", reply)
        return reply

    if not db.list_places(conn, user["id"]):
        db.set_user_state(conn, user["id"], "awaiting_address")
        db.log_message(conn, user["id"], "in", text)
        db.log_message(conn, user["id"], "out", templates.ONBOARDING_GREETING)
        return templates.ONBOARDING_GREETING

    if llm_client is None:
        if not config.ANTHROPIC_API_KEY:
            reply = templates.AGENT_UNAVAILABLE_TEXT
            db.log_message(conn, user["id"], "in", text)
            db.log_message(conn, user["id"], "out", reply)
            return reply
        llm_client = agent.AnthropicLLMClient()

    return agent.run_turn(conn, user, stripped, llm_client)
