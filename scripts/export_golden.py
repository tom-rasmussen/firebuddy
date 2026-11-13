"""Export golden outputs from the Python engine for the Worker's parity tests.

Runs geo, assess and templates over fixed cases and writes worker/test/golden.json.
The TypeScript port must reproduce every output exactly (constitution, quality gate 2).

    PYTHONPATH=. python scripts/export_golden.py
"""

import json
from datetime import datetime
from pathlib import Path

from firebuddy import assess, geo, templates

OUT = Path(__file__).resolve().parent.parent / "worker" / "test" / "golden.json"

HOME = (37.8216, -122.0001)  # Danville fixture point
POINTS = [
    (37.8216, -121.8353),  # Morgan fixture fire (east)
    (37.8183, -121.9623),  # Diablo Rd fixture (near)
    (37.95, -122.05),  # north-northwest
    (37.70, -122.10),  # south-southwest
    (37.8216, -122.0001),  # same point
    (38.5816, -121.4944),  # Sacramento (far)
]


def py_round(x, nd):
    return round(x, nd)


def geo_cases():
    out = []
    for lat, lon in POINTS:
        d = geo.haversine_mi(HOME[0], HOME[1], lat, lon)
        b = geo.bearing_deg(HOME[0], HOME[1], lat, lon)
        out.append(
            {
                "from": list(HOME),
                "to": [lat, lon],
                "distance_mi": d,
                "distance_mi_r1": py_round(d, 1),
                "bearing_deg": b,
                "bearing_deg_r1": py_round(b, 1),
                "compass": geo.compass_16(b),
            }
        )
    compass = {str(d): geo.compass_16(d) for d in [0, 11.24, 11.25, 22.5, 90, 180, 191.25, 348.75, 359.9, 360, 725]}
    diffs = [[a, b, geo.angular_diff(a, b)] for a, b in [(0, 0), (10, 350), (350, 10), (90, 270), (45, 225.5), (720, 30)]]
    rounding = [[x, 1, py_round(x, 1)] for x in [0.25, 0.75, 1.25, 2.25, 2.35, 0.15, 9.05, 8.95, 12.5, 3.14159]]
    return {"pairs": out, "compass": compass, "angular_diff": diffs, "round": rounding}


def make_fire(name, distance_mi, bearing_deg, acres=40, contained=0, updated="2026-10-25T16:12:00-07:00"):
    return {
        "key": f"key-{name}",
        "name": name,
        "acres": acres,
        "percent_contained": contained,
        "distance_mi": distance_mi,
        "direction": geo.compass_16(bearing_deg),
        "bearing_deg": bearing_deg,
        "discovered": "2026-10-25T15:52:00-07:00",
        "updated": updated,
        "source": "NIFC",
    }


def make_alert(event, headline=None, instruction=None, description="Description text.", sent="2026-10-25T16:00:00-07:00"):
    return {
        "id": f"urn:{event}",
        "event": event,
        "headline": headline if headline is not None else f"{event} issued for Contra Costa County",
        "description": description,
        "instruction": instruction,
        "sent": sent,
        "expires": "2026-10-25T20:00:00-07:00",
        "sender_name": "NWS San Francisco Bay Area CA",
        "severity": "Severe",
        "urgency": "Expected",
        "area_desc": "Contra Costa County",
    }


def assess_cases():
    now = datetime.fromisoformat("2026-10-25T17:00:00-07:00")
    wind_rel = [
        [w, s, b, assess.wind_relation(w, s, b)]
        for w, s, b in [
            (90, 14, 90),
            (90, 14, 135),
            (90, 14, 136),
            (90, 14, 170),
            (90, 14, 180),
            (90, 14, 181),
            (90, 14, 260),
            (90, 3, 90),
            (90, 5, 90),
            (None, 14, 90),
            (90, None, 90),
            (350, 20, 10),
        ]
    ]
    stale = [
        [t, assess.wind_is_stale(t, now)]
        for t in [None, "2026-10-25T16:30:00-07:00", "2026-10-25T15:00:00-07:00", "2026-10-25T14:59:00-07:00", "2026-10-25T23:00:00Z"]
    ]
    near = make_fire("Morgan Fire", 3.2, 90.0)
    far = make_fire("Morgan Fire", 9.0, 90.0)
    other = make_fire("Ridge Fire", 12.4, 200.0)
    red = make_alert("Red Flag Warning", instruction="Avoid outdoor burning.")
    evac = make_alert("Evacuation Immediate", instruction="Leave now via official routes.")
    firew = make_alert("Fire Warning", instruction="Evacuate now.")
    shelter = make_alert("Shelter In Place Warning", instruction="Stay indoors. Close all windows.")
    shelter_noinst = make_alert("Shelter In Place Warning", instruction=None, description="Shelter in place until further notice.")
    situations = {
        "nothing": ([], [], None, False),
        "far_fire_wind_away": ([far], [], "away", False),
        "far_fire_wind_unknown": ([far], [], None, False),
        "far_fire_wind_toward": ([far], [], "toward", False),
        "near_fire": ([near], [], "away", False),
        "two_fires_nearest_first": ([other, far], [], "crosswind", False),
        "red_flag_no_fire": ([], [red], None, False),
        "red_flag_with_far_fire": ([far], [red], "away", False),
        "evac_order": ([far], [red, evac], "toward", False),
        "fire_warning": ([], [firew], None, False),
        "user_reports_order": ([far], [], None, True),
        "shelter_in_place": ([near], [shelter], "toward", False),
        "shelter_no_instruction": ([], [shelter_noinst], None, False),
        "shelter_and_evac": ([near], [shelter, evac], None, False),
    }
    assessed = {}
    for name, (fires, alerts, rel, user_order) in situations.items():
        assessed[name] = {
            "input": {"fires": fires, "alerts": alerts, "wind_relation": rel, "user_reports_evac_order": user_order},
            "output": assess.assess_situation(fires, alerts, rel, user_order),
        }
    wind = {
        "station_id": "KCCR",
        "station_distance_mi": 8.1,
        "obs_time": "2026-10-25T16:30:00-07:00",
        "wind_from_deg": 90,
        "wind_speed_mph": 14.0,
        "wind_gust_mph": 25.0,
        "forecast_hourly": [{"start_time": "2026-10-25T18:00:00-07:00", "wind_speed": "10 mph", "wind_direction": "NW"}],
    }
    wind_checks = [
        {"wind": wind, "bearing": 90.0, "output": assess.wind_check(wind, 90.0, now)},
        {"wind": wind, "bearing": None, "output": assess.wind_check(wind, None, now)},
        {"wind": {**wind, "obs_time": "2026-10-25T13:00:00-07:00"}, "bearing": 260.0, "output": assess.wind_check({**wind, "obs_time": "2026-10-25T13:00:00-07:00"}, 260.0, now)},
    ]
    return {"now": now.isoformat(), "wind_relation": wind_rel, "stale": stale, "situations": assessed, "wind_check": wind_checks}


def template_cases():
    tz = "America/Los_Angeles"
    times = [
        [t, z, templates.format_time(t, z)]
        for t, z in [
            ("2026-10-25T16:00:00-07:00", None),
            ("2026-10-25T16:00:00-07:00", tz),
            ("2026-10-25T23:05:00Z", tz),
            ("2026-12-01T00:30:00Z", tz),
            ("2026-10-25T12:00:00-07:00", "America/Denver"),
            ("2026-01-15T09:07:00-07:00", "America/Denver"),
            ("2026-10-25T16:00:00-07:00", "UTC"),
            (None, tz),
        ]
    ]
    f40 = make_fire("Morgan Fire", 9.0, 90.0)
    f150 = make_fire("Morgan Fire", 9.0, 90.0, acres=150, contained=5)
    f_frac = make_fire("Morgan Fire", 9.0, 90.0, acres=152.7, contained=12.5)
    f_none = {**make_fire("Unknown Fire", 4.25, 300.0), "acres": None, "percent_contained": None}
    f_done = make_fire("Morgan Fire", 9.0, 90.0, acres=1210, contained=100)
    red = make_alert("Red Flag Warning", headline="Red Flag Warning issued for Contra Costa County", instruction="Avoid outdoor burning.")
    same = make_alert("Red Flag Warning", headline="Red Flag Warning issued", instruction="Red Flag Warning issued")
    no_body = make_alert("Fire Weather Watch", instruction=None, description=None)
    long_alert = make_alert("Evacuation Immediate", instruction="Leave now. " + "Follow law enforcement direction and use designated routes only. " * 12)
    note = templates.no_other_nws_alerts_note()
    alerts = {
        "new_fire": templates.new_fire_alert("Home", f40, note, tz),
        "new_fire_none_values": templates.new_fire_alert("Home", f_none, note, tz),
        "growth_100": templates.growth_alert("Home", f150, 100, tz),
        "growth_1000_frac": templates.growth_alert("Home", f_frac, 1000, tz),
        "growth_10000": templates.growth_alert("Parents", f150, 10000, tz),
        "containment": templates.containment_alert("Home", f_done, tz),
        "official_red_flag": templates.official_alert_text("Home", red, tz),
        "official_same_text": templates.official_alert_text("Home", same, tz),
        "official_no_body": templates.official_alert_text("Home", no_body, tz),
        "official_long": templates.official_alert_text("Home", long_alert, tz),
    }
    base_wind = {
        "station_id": "KCCR",
        "obs_time": "2026-10-25T16:30:00-07:00",
        "wind_from_deg": 90,
        "wind_speed_mph": 14.0,
        "wind_gust_mph": 25.0,
        "relation_to_fire": "toward",
        "relative_to_fire": "Morgan Fire",
        "stale": False,
        "forecast_hourly": [{"start_time": "2026-10-25T18:00:00-07:00", "wind_speed": "10 to 15 mph", "wind_direction": "NW"}],
    }
    winds = {
        "full_toward": base_wind,
        "no_gust_away": {**base_wind, "wind_gust_mph": None, "relation_to_fire": "away", "wind_speed_mph": 8.5},
        "crosswind_stale": {**base_wind, "relation_to_fire": "crosswind", "stale": True},
        "light": {**base_wind, "wind_speed_mph": 3.0, "relation_to_fire": "light_variable", "relative_to_fire": None},
        "relation_without_fire": {**base_wind, "relative_to_fire": None},
        "no_station": {**base_wind, "station_id": None},
        "gust_only": {**base_wind, "wind_from_deg": None, "wind_speed_mph": None},
        "forecast_only": {**base_wind, "wind_from_deg": None, "wind_speed_mph": None, "wind_gust_mph": None},
        "unavailable": {"wind_from_deg": None, "wind_speed_mph": None, "wind_gust_mph": None, "forecast_hourly": []},
    }
    wind_lines = {k: {"wind": v, "text": templates.wind_line(v, tz)} for k, v in winds.items()}
    statuses = {
        "calm": templates.status_update("Home", [], [], None, tz),
        "fire_and_alert_with_wind": templates.status_update("Home", [f150], [red], base_wind, tz),
    }
    fires = {"f40": f40, "f150": f150, "f_frac": f_frac, "f_none": f_none, "f_done": f_done}
    alert_inputs = {"red": red, "same": same, "no_body": no_body, "long": long_alert}
    return {
        "tz": tz,
        "format_time": times,
        "fires": fires,
        "alert_inputs": alert_inputs,
        "alerts": alerts,
        "wind_lines": wind_lines,
        "status": statuses,
        "status_inputs": {"wind": base_wind},
        "constants": {
            "feel_unsafe": templates.FEEL_UNSAFE_LINE,
            "no_other_alerts": note,
            "guidance": assess.GUIDANCE_TEXT,
        },
    }


def main():
    data = {"geo": geo_cases(), "assess": assess_cases(), "templates": template_cases()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
