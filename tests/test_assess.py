from datetime import datetime, timedelta, timezone

from firebuddy import assess


def make_fire(distance_mi, name="Morgan Fire"):
    return {"name": name, "distance_mi": distance_mi, "direction": "E", "bearing_deg": 90.0}


def make_alert(event, **kw):
    base = {
        "id": f"urn:{event}",
        "event": event,
        "headline": f"{event} headline",
        "description": "desc",
        "instruction": f"{event} instruction text",
        "sent": "2026-10-25T16:00:00-07:00",
        "expires": "2026-10-25T20:00:00-07:00",
        "sender_name": "NWS",
        "severity": "Severe",
        "urgency": "Expected",
        "area_desc": "area",
    }
    base.update(kw)
    return base


# --- wind_relation ---

def test_wind_relation_toward():
    assert assess.wind_relation(90, 14, 90) == "toward"


def test_wind_relation_toward_boundary_45deg():
    assert assess.wind_relation(90, 14, 135) == "toward"


def test_wind_relation_crosswind():
    assert assess.wind_relation(90, 14, 170) == "crosswind"


def test_wind_relation_away():
    assert assess.wind_relation(90, 14, 260) == "away"


def test_wind_relation_light_variable_overrides_direction():
    assert assess.wind_relation(90, 3, 90) == "light_variable"


def test_wind_relation_unknown_missing_direction():
    assert assess.wind_relation(None, 14, 90) == "unknown"


def test_wind_relation_unknown_missing_speed():
    assert assess.wind_relation(90, None, 90) == "unknown"


# --- wind_is_stale ---

def test_wind_is_stale_recent_not_stale():
    now = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
    obs = (now - timedelta(minutes=30)).isoformat()
    assert assess.wind_is_stale(obs, now) is False


def test_wind_is_stale_old_is_stale():
    now = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
    obs = (now - timedelta(hours=3)).isoformat()
    assert assess.wind_is_stale(obs, now) is True


def test_wind_is_stale_missing_obs_is_stale():
    now = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
    assert assess.wind_is_stale(None, now) is True


def test_wind_is_stale_boundary_exactly_2h_not_stale():
    now = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
    obs = (now - timedelta(hours=2)).isoformat()
    assert assess.wind_is_stale(obs, now) is False


# --- wind_check ---

def test_wind_check_combines_relation_and_staleness():
    now = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
    wind = {
        "station_id": "KCCR",
        "station_distance_mi": 4.0,
        "obs_time": (now - timedelta(minutes=30)).isoformat(),
        "wind_from_deg": 90,
        "wind_speed_mph": 14,
        "wind_gust_mph": 25,
        "forecast_hourly": [{"start_time": "x", "wind_speed": "10 mph", "wind_direction": "E"}],
    }
    result = assess.wind_check(wind, bearing_to_fire_deg=90, now=now)
    assert result["relation_to_fire"] == "toward"
    assert result["stale"] is False
    assert "embers" in result["caveat"]
    assert result["forecast_hourly"] == wind["forecast_hourly"]


def test_wind_check_no_fire_bearing_gives_no_relation():
    now = datetime(2026, 10, 25, 16, 30, tzinfo=timezone.utc)
    wind = {"obs_time": now.isoformat(), "wind_from_deg": 90, "wind_speed_mph": 14}
    result = assess.wind_check(wind, bearing_to_fire_deg=None, now=now)
    assert result["relation_to_fire"] is None


# --- assess_situation: every level ---

def test_level_leave_now_fire_warning():
    result = assess.assess_situation(fires=[], alerts=[make_alert("Fire Warning")])
    assert result["level"] == assess.LEVEL_LEAVE_NOW
    assert result["guidance"] == "Follow the order and leave now."


def test_level_leave_now_evacuation_immediate():
    result = assess.assess_situation(fires=[], alerts=[make_alert("Evacuation Immediate")])
    assert result["level"] == assess.LEVEL_LEAVE_NOW


def test_level_leave_now_user_reported_order():
    result = assess.assess_situation(fires=[], alerts=[], user_reports_evac_order=True)
    assert result["level"] == assess.LEVEL_LEAVE_NOW
    assert any("evacuation order" in f for f in result["facts"])


def test_level_leave_now_beats_shelter_order_if_both_present():
    result = assess.assess_situation(
        fires=[], alerts=[make_alert("Fire Warning"), make_alert("Shelter In Place Warning")]
    )
    assert result["level"] == assess.LEVEL_LEAVE_NOW


def test_level_shelter_order_quotes_instruction_verbatim():
    alert = make_alert("Shelter In Place Warning", instruction="Stay inside and seal your doors and windows.")
    result = assess.assess_situation(fires=[], alerts=[alert])
    assert result["level"] == assess.LEVEL_SHELTER
    assert result["guidance"] == "Stay inside and seal your doors and windows."


def test_level_get_ready_fire_within_5mi():
    result = assess.assess_situation(fires=[make_fire(3)], alerts=[])
    assert result["level"] == assess.LEVEL_GET_READY


def test_level_get_ready_fire_in_radius_and_wind_toward():
    result = assess.assess_situation(fires=[make_fire(9)], alerts=[], wind_relation_to_nearest_fire="toward")
    assert result["level"] == assess.LEVEL_GET_READY


def test_level_get_ready_fire_in_radius_and_red_flag():
    result = assess.assess_situation(
        fires=[make_fire(9)], alerts=[make_alert("Red Flag Warning")], wind_relation_to_nearest_fire="away"
    )
    assert result["level"] == assess.LEVEL_GET_READY


def test_level_be_ready_fire_in_radius_wind_not_toward_no_red_flag():
    result = assess.assess_situation(fires=[make_fire(9)], alerts=[], wind_relation_to_nearest_fire="away")
    assert result["level"] == assess.LEVEL_BE_READY


def test_level_be_ready_red_flag_no_fire():
    result = assess.assess_situation(fires=[], alerts=[make_alert("Red Flag Warning")])
    assert result["level"] == assess.LEVEL_BE_READY


def test_level_monitor_nothing_nearby():
    result = assess.assess_situation(fires=[], alerts=[])
    assert result["level"] == assess.LEVEL_MONITOR
    assert result["facts"] == []


def test_level_get_ready_beats_be_ready_when_both_conditions_present():
    # fire within 5mi AND red flag -> still GET READY, not double counted as BE READY
    result = assess.assess_situation(fires=[make_fire(3)], alerts=[make_alert("Red Flag Warning")])
    assert result["level"] == assess.LEVEL_GET_READY
