import json
from typing import Callable

from firebuddy import db, templates
from firebuddy.sources import fires as fires_source
from firebuddy.sources import nws as nws_source

SendFn = Callable[[str, str], None]

NWS_ALERT_EVENTS = {
    "Fire Warning",
    "Evacuation Immediate",
    "Red Flag Warning",
    "Fire Weather Watch",
    "Shelter In Place Warning",
    "Civil Emergency Message",
    "Local Area Emergency",
}


def _check_fires(conn, place, send_fn: SendFn) -> None:
    incidents = fires_source.fires_near(place["lat"], place["lon"], place["radius_mi"])
    for fire in incidents:
        key = fire.get("key")
        if not key:
            continue
        acres = fire.get("acres") or 0
        contained = fire.get("percent_contained")
        state = db.get_incident_state(conn, place["id"], key)

        if state is None:
            new_key = f"new:{key}"
            if db.mark_sent(conn, place["id"], new_key):
                send_fn(
                    place["user_phone"],
                    templates.new_fire_alert(
                        place["label"], fire, templates.no_other_nws_alerts_note()
                    ),
                )
            already_crossed = [t for t in templates.GROWTH_THRESHOLDS if acres >= t]
            db.upsert_incident_state(conn, place["id"], key, acres, contained, already_crossed)
            continue

        alerted = json.loads(state["alerted_thresholds"])
        for t in templates.GROWTH_THRESHOLDS:
            if acres >= t and t not in alerted:
                growth_key = f"growth:{key}:{t}"
                if db.mark_sent(conn, place["id"], growth_key):
                    send_fn(place["user_phone"], templates.growth_alert(place["label"], fire, t))
                alerted.append(t)

        if contained == 100:
            contain_key = f"contain:{key}"
            if db.mark_sent(conn, place["id"], contain_key):
                send_fn(place["user_phone"], templates.containment_alert(place["label"], fire))

        db.upsert_incident_state(conn, place["id"], key, acres, contained, alerted)


def _check_official_alerts(conn, place, send_fn: SendFn) -> None:
    alerts = nws_source.official_alerts(place["lat"], place["lon"])
    for alert in alerts:
        if alert.get("event") not in NWS_ALERT_EVENTS:
            continue
        key = f"nws:{alert['id']}"
        if db.mark_sent(conn, place["id"], key):
            send_fn(place["user_phone"], templates.official_alert_text(place["label"], alert))


def _check_followups(conn, send_fn: SendFn) -> None:
    for followup in db.due_followups(conn):
        place = db.get_place(conn, followup["place_id"])
        if place is None or not place["active"]:
            db.mark_followup_done(conn, followup["id"])
            continue
        fires_list = fires_source.fires_near(place["lat"], place["lon"], place["radius_mi"])
        alerts_list = nws_source.official_alerts(place["lat"], place["lon"])
        send_fn(followup["user_phone"], templates.status_update(place["label"], fires_list, alerts_list))
        db.mark_followup_done(conn, followup["id"])


def run_once(conn, send_fn: SendFn) -> None:
    for place in db.list_active_places_all_users(conn):
        _check_fires(conn, place, send_fn)
        _check_official_alerts(conn, place, send_fn)
    _check_followups(conn, send_fn)
