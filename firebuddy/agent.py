import json
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

from firebuddy import clock, config, db, assess
from firebuddy.sources import fires as fires_source
from firebuddy.sources import geocode
from firebuddy.sources import nws as nws_source
from firebuddy.sources import shelters as shelters_source

MAX_TOOL_ITERATIONS = 6
MAX_REPLY_CHARS = 480

SYSTEM_PROMPT = """You are FireBuddy, an SMS wildfire assistant.

Hard rules, never break them:
- Every fact and number in your reply must come from a tool result you received this turn, \
or from the user's own message. Never invent a number, distance, acreage, percentage, or time.
- Never say "you're safe", "it's safe", "no need to leave", or "you can stay" — unless you are \
quoting an official shelter-in-place order verbatim from a tool result.
- Never invent driving routes or directions. If official text names a route, quote it; \
otherwise point the user to official sources (emergency_resources tool).
- Quote official alert text (headline/instruction) word for word, with its source and time. \
Never paraphrase an official order.
- The guidance level from assess_situation is deterministic. You may ESCALATE it in your \
wording (e.g. if the user says they see flames or smell smoke) but you may NEVER de-escalate it.
- Always end every substantive reply with: "If you're in immediate danger, call 911. If you \
feel unsafe, leave. You don't need to wait for an order." Include a zone-lookup link \
(from emergency_resources) when relevant.
- State uncertainty plainly when data is stale, missing, or incomplete.
- Keep replies plain text, no markdown, no asterisks. Aim for 480 characters or less; \
longer is fine for "should I leave" or shelter-list answers.
- Use the tools to get facts. Don't guess. If an address is ambiguous, ask a short clarifying \
question instead of guessing a location.

Deterministic SMS commands (ADD/LIST/REMOVE/RADIUS/STATUS/STOP/START/HELP) are handled outside \
of you by a router. You only see free-form questions and conversational requests.
"""

TOOL_SCHEMAS = [
    {
        "name": "list_places",
        "description": "List the user's watched places (id, label, address, radius).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_place",
        "description": "Add a new place to watch for wildfires.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Street address, town, or landmark."},
                "label": {"type": "string", "description": "Short label, e.g. 'Home' or 'Parents'."},
                "radius_mi": {"type": "number", "description": "Watch radius in miles, 1-50. Default 15."},
            },
            "required": ["address"],
        },
    },
    {
        "name": "remove_place",
        "description": "Stop watching a place.",
        "input_schema": {
            "type": "object",
            "properties": {"place_id": {"type": "integer"}},
            "required": ["place_id"],
        },
    },
    {
        "name": "set_radius",
        "description": "Change the watch radius (miles) for a place.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "integer"},
                "radius_mi": {"type": "number", "description": "1-50"},
            },
            "required": ["place_id", "radius_mi"],
        },
    },
    {
        "name": "fires_near",
        "description": "Active wildfire incidents near a place: name, acres, % contained, "
        "distance, direction, discovered/updated times, source.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "integer"},
                "radius_mi": {"type": "number", "description": "Override the place's default radius."},
            },
            "required": ["place_id"],
        },
    },
    {
        "name": "official_alerts",
        "description": "Active official NWS alerts (fire warnings, evacuation orders, red flag "
        "warnings, shelter-in-place, etc.) covering a place's point.",
        "input_schema": {
            "type": "object",
            "properties": {"place_id": {"type": "integer"}},
            "required": ["place_id"],
        },
    },
    {
        "name": "wind_check",
        "description": "Current wind observation and 12h forecast near a place, plus whether "
        "the wind is blowing toward/crosswind/away from a given (or the nearest) fire.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "integer"},
                "incident_name": {"type": "string", "description": "Optional specific fire name."},
            },
            "required": ["place_id"],
        },
    },
    {
        "name": "assess_situation",
        "description": "The deterministic 'should I leave?' guidance level for a place: "
        "LEAVE NOW / FOLLOW SHELTER ORDER / GET READY / BE READY / MONITOR, with the facts "
        "that triggered it and the standard guidance text. You may escalate this in wording, "
        "never de-escalate it.",
        "input_schema": {
            "type": "object",
            "properties": {"place_id": {"type": "integer"}},
            "required": ["place_id"],
        },
    },
    {
        "name": "find_shelters",
        "description": "Open FEMA National Shelter System shelters nearest a place.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "integer"},
                "max_results": {"type": "integer", "description": "Default 3."},
            },
            "required": ["place_id"],
        },
    },
    {
        "name": "schedule_followup",
        "description": "Schedule a status check-in text for a place in the future.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "integer"},
                "hours": {"type": "number", "description": "0.5-24 hours from now."},
                "note": {"type": "string", "description": "What to remind about."},
            },
            "required": ["place_id", "hours", "note"],
        },
    },
    {
        "name": "emergency_resources",
        "description": "Static emergency links/resources for a place: zone lookup, 911, 211, "
        "NWS alerts page, county OES lookup.",
        "input_schema": {
            "type": "object",
            "properties": {"place_id": {"type": "integer"}},
            "required": ["place_id"],
        },
    },
]


# --- tool implementations ---

def _owned_place(conn, user_id: int, place_id):
    if place_id is None:
        return None
    place = db.get_place(conn, place_id)
    if place is None or place["user_id"] != user_id or not place["active"]:
        return None
    return place


def _default_label(conn, user_id: int) -> str:
    existing = db.list_places(conn, user_id)
    return "Home" if not existing else f"Place {len(existing) + 1}"


def _resolve_fire_and_bearing(place, incident_name: str | None):
    incidents = fires_source.fires_near(place["lat"], place["lon"], place["radius_mi"])
    if not incidents:
        return None, None
    if incident_name:
        matches = [f for f in incidents if incident_name.lower() in f["name"].lower()]
        target = matches[0] if matches else min(incidents, key=lambda f: f["distance_mi"])
    else:
        target = min(incidents, key=lambda f: f["distance_mi"])
    return target, target["bearing_deg"]


def _tool_list_places(conn, user_id, _input):
    places = db.list_places(conn, user_id)
    return {
        "places": [
            {"place_id": p["id"], "label": p["label"], "address": p["address"], "radius_mi": p["radius_mi"]}
            for p in places
        ]
    }


def _tool_add_place(conn, user_id, input):
    address = (input.get("address") or "").strip()
    if not address:
        return {"error": "Please provide an address or town to watch."}
    try:
        loc = geocode.geocode(address)
    except geocode.GeocodeError:
        return {
            "error": f"I couldn't find '{address}'. Can you give a more specific address, "
            "or the nearest town and state?"
        }
    radius_mi = input.get("radius_mi") or 15
    radius_mi = max(1, min(50, radius_mi))
    label = (input.get("label") or "").strip() or _default_label(conn, user_id)
    place = db.add_place(conn, user_id, label, loc["matched_address"], loc["lat"], loc["lon"], radius_mi)
    return {
        "place_id": place["id"],
        "label": place["label"],
        "address": place["address"],
        "radius_mi": place["radius_mi"],
    }


def _tool_remove_place(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    db.remove_place(conn, place["id"])
    return {"ok": True}


def _tool_set_radius(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    radius_mi = input.get("radius_mi")
    if radius_mi is None:
        return {"error": "radius_mi is required."}
    radius_mi = max(1, min(50, radius_mi))
    db.set_radius(conn, place["id"], radius_mi)
    return {"ok": True, "radius_mi": radius_mi}


def _tool_fires_near(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    radius_mi = input.get("radius_mi") or place["radius_mi"]
    incidents = fires_source.fires_near(place["lat"], place["lon"], radius_mi)
    return {"place_label": place["label"], "radius_mi": radius_mi, "incidents": incidents}


def _tool_official_alerts(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    alerts = nws_source.official_alerts(place["lat"], place["lon"])
    return {"place_label": place["label"], "alerts": alerts}


def _tool_wind_check(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    wind = nws_source.wind_data(place["lat"], place["lon"])
    target_fire, bearing = _resolve_fire_and_bearing(place, input.get("incident_name"))
    result = assess.wind_check(wind, bearing, now=clock.now())
    result["place_label"] = place["label"]
    if target_fire:
        result["relative_to_fire"] = target_fire["name"]
    return result


def _tool_assess_situation(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    incidents = fires_source.fires_near(place["lat"], place["lon"], place["radius_mi"])
    alerts = nws_source.official_alerts(place["lat"], place["lon"])
    relation = None
    if incidents:
        wind = nws_source.wind_data(place["lat"], place["lon"])
        _, bearing = _resolve_fire_and_bearing(place, None)
        if bearing is not None:
            relation = assess.wind_relation(wind.get("wind_from_deg"), wind.get("wind_speed_mph"), bearing)
    result = assess.assess_situation(incidents, alerts, wind_relation_to_nearest_fire=relation)
    result["place_label"] = place["label"]
    result["incidents"] = incidents
    result["alerts"] = alerts
    return result


def _tool_find_shelters(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    max_results = input.get("max_results") or 3
    shelters = shelters_source.find_shelters(place["lat"], place["lon"], max_results)
    return {"place_label": place["label"], "shelters": shelters}


def _tool_schedule_followup(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    hours = input.get("hours")
    if hours is None:
        return {"error": "hours is required."}
    hours = max(0.5, min(24, hours))
    due_at = (clock.now() + timedelta(hours=hours)).isoformat()
    db.schedule_followup(conn, user_id, place["id"], due_at, input.get("note") or "")
    return {"due_at": due_at, "hours": hours}


def _tool_emergency_resources(conn, user_id, input):
    place = _owned_place(conn, user_id, input.get("place_id"))
    if place is None:
        return {"error": "Place not found."}
    return {
        "zone_lookup": "https://protect.genasys.com/search",
        "emergency": "911",
        "info_211": "211",
        "nws_alerts_page": "https://api.weather.gov/alerts/active",
        "county_oes_note": "Search '<your county> office of emergency services' or call 211 "
        "for shelter and evacuation info.",
    }


TOOL_DISPATCH = {
    "list_places": _tool_list_places,
    "add_place": _tool_add_place,
    "remove_place": _tool_remove_place,
    "set_radius": _tool_set_radius,
    "fires_near": _tool_fires_near,
    "official_alerts": _tool_official_alerts,
    "wind_check": _tool_wind_check,
    "assess_situation": _tool_assess_situation,
    "find_shelters": _tool_find_shelters,
    "schedule_followup": _tool_schedule_followup,
    "emergency_resources": _tool_emergency_resources,
}


def execute_tool(conn, user_id: int, name: str, tool_input: dict) -> dict:
    handler = TOOL_DISPATCH.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(conn, user_id, tool_input or {})
    except Exception as exc:  # live API hiccup, bad input, etc. — never crash the turn
        return {"error": f"{name} failed: {exc}"}


# --- LLM client abstraction ---

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict = field(default_factory=dict)
    type: str = "tool_use"


@dataclass
class FakeMessage:
    content: list
    stop_reason: str
    usage: Usage = field(default_factory=Usage)


class FakeLLMClient:
    """Scripted LLM for tests: pass a list of FakeMessage responses to return in order."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list = []

    def create(self, *, system, messages, tools, max_tokens=1024):
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        if not self._responses:
            raise RuntimeError("FakeLLMClient exhausted its scripted responses")
        return self._responses.pop(0)


class AnthropicLLMClient:
    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        import anthropic

        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def create(self, *, system, messages, tools, max_tokens=1024):
        return self._client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )


# --- grounding validator ---

TIME_PATTERN = re.compile(r"\b\d{1,2}(:\d{2})?\s*(AM|PM|am|pm)\b")
NUMBER_PATTERN = re.compile(r"\d[\d,]*\.?\d*")
# Fixed emergency numbers from the mandatory safety line / emergency_resources tool.
# These are constants dictated by the system prompt, not situational facts that could
# be hallucinated wrong, so they're exempt from the "every number must be grounded" check.
SAFE_NUMBER_CONSTANTS = {"911", "211"}
BLOCKED_PHRASES = [
    re.compile(r"you'?re safe", re.IGNORECASE),
    re.compile(r"it'?s safe", re.IGNORECASE),
    re.compile(r"no need to leave", re.IGNORECASE),
    re.compile(r"you can stay", re.IGNORECASE),
    re.compile(r"take\s+(I-|Hwy|Highway|Route|SR|US)\s?\d+", re.IGNORECASE),
]


@dataclass
class ValidatorResult:
    ok: bool
    reason: str | None = None


def _extracted_numbers(text: str) -> list[str]:
    without_times = TIME_PATTERN.sub(" ", text)
    numbers = (m.group().replace(",", "").rstrip(".") for m in NUMBER_PATTERN.finditer(without_times))
    return [n for n in numbers if n not in SAFE_NUMBER_CONSTANTS]


def validate(final_text: str, grounding_blob: str, user_text: str) -> ValidatorResult:
    if not final_text or not final_text.strip():
        return ValidatorResult(ok=False, reason="empty reply")

    haystack = (grounding_blob + "\n" + user_text).replace(",", "")
    for num in _extracted_numbers(final_text):
        if num not in haystack:
            return ValidatorResult(ok=False, reason=f"ungrounded number: {num}")

    for pattern in BLOCKED_PHRASES:
        match = pattern.search(final_text)
        if match and match.group() not in grounding_blob:
            return ValidatorResult(ok=False, reason=f"unquoted blocked phrase: {match.group()!r}")

    return ValidatorResult(ok=True)


def _fallback_text(tool_calls: list[dict], places) -> str:
    fires_list, alerts_list, label = [], [], (places[0]["label"] if places else "your place")
    for call in reversed(tool_calls):
        result = call.get("result") or {}
        if "incidents" in result and not fires_list:
            fires_list = result["incidents"]
            label = result.get("place_label", label)
        if "alerts" in result and not alerts_list:
            alerts_list = result["alerts"]
    from firebuddy import templates

    status = templates.status_update(label, fires_list, alerts_list)
    return f"{status}\nI couldn't verify a full answer. Here's what I know for sure."


def _extract_text(message) -> str:
    return "".join(block.text for block in message.content if block.type == "text").strip()


def _block_to_dict(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}


def build_system_prompt(places) -> str:
    if not places:
        places_bit = "This user has no watched places yet."
    else:
        lines = [f"- {p['label']} (id {p['id']}): {p['address']}, {p['radius_mi']} mi radius" for p in places]
        places_bit = "This user's watched places:\n" + "\n".join(lines)
    return SYSTEM_PROMPT + "\n" + places_bit


def _history_to_messages(history) -> list[dict]:
    messages = []
    for msg in history:
        role = "user" if msg["direction"] == "in" else "assistant"
        messages.append({"role": role, "content": msg["body"]})
    return messages


def _drive_tool_loop(conn, user_id, messages, call_llm, response, tool_calls_trace, grounding_parts):
    """Resolve tool_use responses until the model produces text or hits MAX_TOOL_ITERATIONS."""
    iterations = 0
    while response.stop_reason == "tool_use" and iterations < MAX_TOOL_ITERATIONS:
        iterations += 1
        messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in response.content]})
        tool_result_blocks = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = execute_tool(conn, user_id, block.name, block.input)
            tool_calls_trace.append({"name": block.name, "input": block.input, "result": result})
            grounding_parts.append(json.dumps(result, default=str))
            tool_result_blocks.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)}
            )
        messages.append({"role": "user", "content": tool_result_blocks})
        response = call_llm(messages)
    return response


def run_turn(conn, user, user_text: str, llm_client) -> str:
    places = db.list_places(conn, user["id"])
    history = db.recent_messages(conn, user["id"], limit=12)
    system = build_system_prompt(places)
    messages = _history_to_messages(history) + [{"role": "user", "content": user_text}]

    tool_calls_trace: list[dict] = []
    grounding_parts: list[str] = []
    usage = Usage()
    start = time.monotonic()

    def call_llm(msgs):
        resp = llm_client.create(system=system, messages=msgs, tools=TOOL_SCHEMAS, max_tokens=1024)
        usage.input_tokens += getattr(resp.usage, "input_tokens", 0) or 0
        usage.output_tokens += getattr(resp.usage, "output_tokens", 0) or 0
        return resp

    response = call_llm(messages)
    response = _drive_tool_loop(
        conn, user["id"], messages, call_llm, response, tool_calls_trace, grounding_parts
    )

    final_text = _extract_text(response)
    grounding_blob = "\n".join(grounding_parts)
    result = validate(final_text, grounding_blob, user_text)
    retries = 0

    if not result.ok:
        retries = 1
        correction = (
            f"Your previous reply failed a grounding check ({result.reason}). Reply again using "
            "only facts/numbers from this turn's tool results or the user's message. Quote official "
            "alert text exactly if you restate it."
        )
        messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in response.content]})
        messages.append({"role": "user", "content": correction})
        response = call_llm(messages)
        response = _drive_tool_loop(
            conn, user["id"], messages, call_llm, response, tool_calls_trace, grounding_parts
        )
        grounding_blob = "\n".join(grounding_parts)
        retry_text = _extract_text(response)
        retry_result = validate(retry_text, grounding_blob, user_text)
        if retry_result.ok:
            final_text = retry_text
            result = retry_result
        else:
            final_text = _fallback_text(tool_calls_trace, places)
            result = retry_result

    latency_ms = (time.monotonic() - start) * 1000
    db.log_message(conn, user["id"], "in", user_text)
    db.log_message(conn, user["id"], "out", final_text)
    db.log_trace(
        conn,
        user["id"],
        user_text,
        tool_calls_trace,
        final_text,
        f"{'ok' if result.ok else 'failed'}: {result.reason or ''}".strip(": "),
        retries,
        latency_ms,
        usage.input_tokens,
        usage.output_tokens,
    )
    return final_text
