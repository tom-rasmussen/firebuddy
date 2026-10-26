"""Console simulator for FireBuddy. Chat as a user, and use : commands to control the
simulated world (fires, alerts, wind, shelters, clock) without hitting any live API.

Usage: python sim.py
"""

import sys

from firebuddy import agent, clock, config, db, geo, monitor, router, sms
from firebuddy.sources import fires as fires_source
from firebuddy.sources import nws as nws_source
from firebuddy.sources import shelters as shelters_source

SIM_PHONE = "+15555550123"

WORLD = {"fires": {}, "alerts": {}, "wind": None, "shelters": []}

SIM_HELP = """Sim commands:
  :fire <name> <acres> <dist_mi> <dir16> [bearing_deg]  add/update a fire
  :grow <name> <acres>                                   change a fire's acreage
  :contain <name> <percent>                               change a fire's % contained
  :nws <event|alias> [headline text...]                   add/replace an NWS alert
      aliases: firewarning evac redflag fireweather shelterinplace civil local
  :clearnws                                                clear all NWS alerts
  :wind <from_deg> <speed_mph> [gust_mph]                 set current wind observation
  :shelter <name...> open|closed                           add/update a shelter (status is the last word)
  :tick                                                    run the monitor loop once now
  :advance <hours>                                         advance the clock, then :tick
  :help                                                    this message
  :quit                                                    exit
Anything else is sent as an SMS from the simulated user (+15555550123)."""


def _bearing_for_compass(label: str) -> float:
    try:
        return geo.COMPASS_POINTS.index(label.upper()) * 22.5
    except ValueError:
        return 0.0


def _fake_fires_near(lat, lon, radius_mi):
    return [f for f in WORLD["fires"].values() if f["distance_mi"] <= radius_mi]


def _fake_official_alerts(lat, lon):
    return list(WORLD["alerts"].values())


def _fake_wind_data(lat, lon):
    return WORLD["wind"] or {
        "station_id": "SIM",
        "station_distance_mi": 0,
        "obs_time": clock.now().isoformat(),
        "wind_from_deg": None,
        "wind_speed_mph": None,
        "wind_gust_mph": None,
        "forecast_hourly": [],
    }


def _fake_find_shelters(lat, lon, max_results=3):
    open_shelters = [s for s in WORLD["shelters"] if s["status"] == "open"]
    return open_shelters[:max_results]


def install_fakes():
    if not config.FIREBUDDY_FIXTURES:
        config.FIREBUDDY_FIXTURES = "fixtures"  # geocoding uses fixtures/geocode.json -> fully offline
    fires_source.fires_near = _fake_fires_near
    nws_source.official_alerts = _fake_official_alerts
    nws_source.wind_data = _fake_wind_data
    shelters_source.find_shelters = _fake_find_shelters


def cmd_fire(args):
    if len(args) < 4:
        print("usage: :fire <name> <acres> <dist_mi> <dir16> [bearing_deg]")
        return
    name, acres, dist_mi, direction = args[0], float(args[1]), float(args[2]), args[3]
    bearing = float(args[4]) if len(args) > 4 else _bearing_for_compass(direction)
    existing = WORLD["fires"].get(name, {})
    WORLD["fires"][name] = {
        "key": name,
        "name": name,
        "acres": acres,
        "percent_contained": existing.get("percent_contained", 0),
        "distance_mi": dist_mi,
        "direction": direction.upper(),
        "bearing_deg": bearing,
        "discovered": clock.now().isoformat(),
        "updated": clock.now().isoformat(),
        "source": "SIM",
    }
    print(f"ok: {name} set ({acres} ac, {dist_mi} mi {direction.upper()})")


def cmd_grow(args):
    name, acres = args[0], float(args[1])
    if name not in WORLD["fires"]:
        print(f"no such fire: {name}")
        return
    WORLD["fires"][name]["acres"] = acres
    WORLD["fires"][name]["updated"] = clock.now().isoformat()
    print(f"ok: {name} -> {acres} ac")


def cmd_contain(args):
    name, pct = args[0], float(args[1])
    if name not in WORLD["fires"]:
        print(f"no such fire: {name}")
        return
    WORLD["fires"][name]["percent_contained"] = pct
    WORLD["fires"][name]["updated"] = clock.now().isoformat()
    print(f"ok: {name} -> {pct}% contained")


NWS_EVENT_ALIASES = {
    "firewarning": "Fire Warning",
    "evac": "Evacuation Immediate",
    "redflag": "Red Flag Warning",
    "fireweather": "Fire Weather Watch",
    "shelterinplace": "Shelter In Place Warning",
    "civil": "Civil Emergency Message",
    "local": "Local Area Emergency",
}


def cmd_nws(args):
    event = NWS_EVENT_ALIASES.get(args[0].lower(), args[0])
    headline = " ".join(args[1:]) or f"{event} in effect"
    WORLD["alerts"][event] = {
        "id": f"urn:sim:{event}",
        "event": event,
        "headline": headline,
        "description": headline,
        "instruction": headline,
        "sent": clock.now().isoformat(),
        "expires": None,
        "sender_name": "SIM",
        "severity": "Severe",
        "urgency": "Expected",
        "area_desc": "Simulated area",
    }
    print(f"ok: {event} added")


def cmd_clearnws(_args):
    WORLD["alerts"].clear()
    print("ok: alerts cleared")


def cmd_wind(args):
    from_deg, speed = float(args[0]), float(args[1])
    gust = float(args[2]) if len(args) > 2 else speed * 1.6
    WORLD["wind"] = {
        "station_id": "SIM",
        "station_distance_mi": 0,
        "obs_time": clock.now().isoformat(),
        "wind_from_deg": from_deg,
        "wind_speed_mph": speed,
        "wind_gust_mph": gust,
        "forecast_hourly": [],
    }
    print(f"ok: wind from {from_deg} deg at {speed} mph")


def cmd_shelter(args):
    name, status = " ".join(args[:-1]), args[-1].lower()
    WORLD["shelters"] = [s for s in WORLD["shelters"] if s["name"] != name]
    WORLD["shelters"].append(
        {"name": name, "address": "123 Shelter Rd", "distance_mi": 2.0, "pets": "Y", "ada": "Y",
         "org": "SIM", "status": status}
    )
    print(f"ok: shelter {name} -> {status}")


def _flush_outbox(skip_body=None):
    for to_phone, body in sms.OUTBOX:
        if body == skip_body:
            continue
        print(f"FB -> {to_phone}: {body}")
    sms.clear_outbox()


def cmd_tick(conn, _args):
    monitor.run_once(conn, sms.send)
    print("ok: monitor tick done")
    _flush_outbox()


def cmd_advance(conn, args):
    hours = float(args[0])
    clock.advance(hours * 3600)
    print(f"ok: clock advanced {hours}h -> {clock.now().isoformat()}")
    cmd_tick(conn, [])


SIM_COMMANDS = {
    ":fire": cmd_fire,
    ":grow": cmd_grow,
    ":contain": cmd_contain,
    ":nws": cmd_nws,
    ":clearnws": cmd_clearnws,
    ":wind": cmd_wind,
}
DB_AWARE_COMMANDS = {":tick": cmd_tick, ":advance": cmd_advance}


def main():
    install_fakes()
    print("FireBuddy simulator. Type :help for sim commands, or chat as the user. :quit to exit.")

    llm_client = agent.AnthropicLLMClient() if config.ANTHROPIC_API_KEY else None
    if llm_client is None:
        print("(ANTHROPIC_API_KEY not set — open-ended questions will use the canned fallback.)")

    with db.session(":memory:") as conn:
        for line in sys.stdin if not sys.stdin.isatty() else iter(lambda: input("> "), ":quit"):
            line = line.strip()
            if not line:
                continue
            if line in (":quit", ":exit"):
                break
            if line == ":help":
                print(SIM_HELP)
                continue
            parts = line.split()
            head = parts[0]
            if head == ":shelter":
                cmd_shelter(parts[1:])
                continue
            if head in SIM_COMMANDS:
                SIM_COMMANDS[head](parts[1:])
                continue
            if head in DB_AWARE_COMMANDS:
                DB_AWARE_COMMANDS[head](conn, parts[1:])
                continue
            if line.startswith(":"):
                print(f"unknown sim command: {head} (try :help)")
                continue

            reply = router.route_message(conn, SIM_PHONE, line, llm_client)
            print(f"FB: {reply if reply else '(no reply)'}")
            _flush_outbox(skip_body=reply)


if __name__ == "__main__":
    main()
