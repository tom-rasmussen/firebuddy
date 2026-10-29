from firebuddy import templates


def test_format_time_converts_to_place_local_zone():
    # 2026-10-26T06:48:00+00:00 is 2026-10-25 23:48 PDT (UTC-7 during daylight time).
    result = templates.format_time("2026-10-26T06:48:00+00:00", "America/Los_Angeles")
    assert result == "11:48 PM PDT"


def test_format_time_defaults_to_default_timezone_when_none_given():
    result = templates.format_time("2026-10-26T06:48:00+00:00")
    assert result.endswith("PDT") or result.endswith("PST")


def test_format_time_falls_back_gracefully_on_bad_timezone():
    result = templates.format_time("2026-10-26T06:48:00+00:00", "Not/AZone")
    assert "AM" in result or "PM" in result  # degrades to a UTC-offset label, doesn't crash


def test_format_time_no_iso_string():
    assert templates.format_time(None) == "time unknown"


def test_official_alert_text_dedupes_identical_headline_and_instruction():
    alert = {
        "event": "Red Flag Warning",
        "headline": "Red Flag Warning issued for Contra Costa County",
        "description": "Red Flag Warning issued for Contra Costa County",
        "instruction": "Red Flag Warning issued for Contra Costa County",
        "sent": "2026-10-26T06:48:00+00:00",
        "sender_name": "SIM",
    }
    text = templates.official_alert_text("Home", alert, "America/Los_Angeles")
    assert text.count("Red Flag Warning issued for Contra Costa County") == 1


def test_official_alert_text_keeps_distinct_headline_and_instruction():
    alert = {
        "event": "Evacuation Immediate",
        "headline": "Evacuation ordered",
        "description": "desc",
        "instruction": "Evacuate immediately via Highway 4 westbound.",
        "sent": "2026-10-26T06:48:00+00:00",
        "sender_name": "SIM",
    }
    text = templates.official_alert_text("Home", alert, "America/Los_Angeles")
    assert "Evacuation ordered" in text
    assert "Evacuate immediately via Highway 4 westbound." in text


def test_wind_line_formats_toward_relation():
    wind = {
        "wind_from_deg": 90,
        "wind_speed_mph": 14,
        "wind_gust_mph": 25,
        "relation_to_fire": "toward",
        "relative_to_fire": "Morgan",
        "station_id": "SIM",
        "obs_time": "2026-10-26T06:48:00+00:00",
        "stale": False,
    }
    line = templates.wind_line(wind, "America/Los_Angeles")
    assert line == "Wind: from E at 14 mph (gusts 25), blowing from Morgan toward you (SIM obs, 11:48 PM PDT)."


def test_wind_line_no_fire_relation():
    wind = {
        "wind_from_deg": 270,
        "wind_speed_mph": 8,
        "wind_gust_mph": None,
        "relation_to_fire": None,
        "relative_to_fire": None,
        "station_id": "KCCR",
        "obs_time": "2026-10-26T06:48:00+00:00",
        "stale": False,
    }
    line = templates.wind_line(wind, "America/Los_Angeles")
    assert line == "Wind: from W at 8 mph (KCCR obs, 11:48 PM PDT)."


def test_wind_line_light_variable_has_no_fire_name_requirement():
    wind = {
        "wind_from_deg": 90,
        "wind_speed_mph": 2,
        "wind_gust_mph": 3,
        "relation_to_fire": "light_variable",
        "relative_to_fire": None,
        "station_id": "SIM",
        "obs_time": "2026-10-26T06:48:00+00:00",
        "stale": False,
    }
    line = templates.wind_line(wind, "America/Los_Angeles")
    assert "light and variable" in line


def test_wind_line_flags_stale():
    wind = {
        "wind_from_deg": 90,
        "wind_speed_mph": 14,
        "wind_gust_mph": 25,
        "relation_to_fire": "toward",
        "relative_to_fire": "Morgan",
        "station_id": "SIM",
        "obs_time": "2026-10-26T06:48:00+00:00",
        "stale": True,
    }
    line = templates.wind_line(wind, "America/Los_Angeles")
    assert "stale" in line


def test_wind_line_missing_observation():
    assert templates.wind_line({"wind_from_deg": None, "wind_speed_mph": None}) == "Wind: observation unavailable."


def test_wind_line_gust_only_observation():
    wind = {
        "wind_from_deg": None,
        "wind_speed_mph": None,
        "wind_gust_mph": 28,
        "station_id": "KOVE",
        "obs_time": "2026-10-26T06:48:00+00:00",
    }
    line = templates.wind_line(wind, "America/Los_Angeles")
    assert line == "Wind: gusts 28 mph, no steady reading (KOVE obs, 11:48 PM PDT)."


def test_wind_line_falls_back_to_forecast():
    wind = {
        "wind_from_deg": None,
        "wind_speed_mph": None,
        "forecast_hourly": [
            {"start_time": "2026-10-26T14:00:00-07:00", "wind_speed": "0 to 3 mph", "wind_direction": "W"},
        ],
    }
    line = templates.wind_line(wind, "America/Los_Angeles")
    assert line == "Wind: forecast W 0 to 3 mph from 2:00 PM PDT."


def test_status_update_includes_wind_line_when_provided():
    wind = {
        "wind_from_deg": 90,
        "wind_speed_mph": 14,
        "wind_gust_mph": 25,
        "relation_to_fire": "toward",
        "relative_to_fire": "Morgan",
        "station_id": "SIM",
        "obs_time": "2026-10-26T06:48:00+00:00",
        "stale": False,
    }
    text = templates.status_update("Home", [], [], wind, "America/Los_Angeles")
    assert "Nothing nearby right now." in text
    assert "Wind: from E at 14 mph" in text


def test_status_update_omits_wind_line_when_not_provided():
    text = templates.status_update("Home", [], [])
    assert "Wind:" not in text
    assert text == "Status check for Home:\nNothing nearby right now."
