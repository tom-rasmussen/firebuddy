import pytest

from firebuddy import db, monitor
from firebuddy.sources import fires as fires_source
from firebuddy.sources import nws as nws_source


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def place(conn):
    user = db.get_or_create_user(conn, "+15550001111")
    return db.add_place(conn, user["id"], "Home", "123 Main St, Danville, CA", 37.82, -122.0, 15)


def make_fire(acres, contained, key="F1"):
    return {
        "key": key,
        "name": "Morgan Fire",
        "acres": acres,
        "percent_contained": contained,
        "distance_mi": 9.0,
        "direction": "E",
        "discovered": "2026-10-25T12:00:00+00:00",
        "updated": "2026-10-25T15:12:00+00:00",
        "source": "NIFC",
    }


def sent_texts(monkeypatch, fire_sequence=None, alert_sequence=None):
    calls = []

    def fake_fires(lat, lon, radius):
        return fire_sequence or []

    def fake_alerts(lat, lon):
        return alert_sequence or []

    def fake_wind_data(lat, lon):
        return {
            "station_id": "TEST",
            "station_distance_mi": 1.0,
            "obs_time": "2026-10-25T15:00:00+00:00",
            "wind_from_deg": 270,
            "wind_speed_mph": 8,
            "wind_gust_mph": 12,
            "forecast_hourly": [],
        }

    def fake_get_timezone(lat, lon):
        return "America/Los_Angeles"

    def fake_send(phone, text):
        calls.append((phone, text))

    monkeypatch.setattr(fires_source, "fires_near", fake_fires)
    monkeypatch.setattr(nws_source, "official_alerts", fake_alerts)
    monkeypatch.setattr(nws_source, "wind_data", fake_wind_data)
    monkeypatch.setattr(nws_source, "get_timezone", fake_get_timezone)
    return calls, fake_send


def test_new_fire_alerts_exactly_once(conn, place, monkeypatch):
    calls, send_fn = sent_texts(monkeypatch, fire_sequence=[make_fire(40, 0)])
    monitor.run_once(conn, send_fn)
    assert len(calls) == 1
    assert "Morgan Fire" in calls[0][1]
    assert "\U0001f525" in calls[0][1]


def test_repeat_run_sends_nothing_new(conn, place, monkeypatch):
    calls, send_fn = sent_texts(monkeypatch, fire_sequence=[make_fire(40, 0)])
    monitor.run_once(conn, send_fn)
    monitor.run_once(conn, send_fn)
    assert len(calls) == 1


def test_growth_past_threshold_alerts_once(conn, place, monkeypatch):
    # Discover the fire small, then grow it past 100 acres on the next tick.
    calls1, send_fn1 = sent_texts(monkeypatch, fire_sequence=[make_fire(40, 0)])
    monitor.run_once(conn, send_fn1)
    assert len(calls1) == 1  # new-fire alert only

    calls2, send_fn2 = sent_texts(monkeypatch, fire_sequence=[make_fire(150, 5)])
    monitor.run_once(conn, send_fn2)
    assert len(calls2) == 1
    assert "Growing fire" in calls2[0][1]
    assert "100" in calls2[0][1]

    # Running again at the same acreage should not re-alert.
    calls3, send_fn3 = sent_texts(monkeypatch, fire_sequence=[make_fire(150, 5)])
    monitor.run_once(conn, send_fn3)
    assert len(calls3) == 0


def test_containment_alerts_once(conn, place, monkeypatch):
    calls1, send_fn1 = sent_texts(monkeypatch, fire_sequence=[make_fire(150, 5)])
    monitor.run_once(conn, send_fn1)  # new-fire alert (already above 100ac at discovery)

    calls2, send_fn2 = sent_texts(monkeypatch, fire_sequence=[make_fire(180, 100)])
    monitor.run_once(conn, send_fn2)
    assert len(calls2) == 1
    assert "100% contained" in calls2[0][1]

    calls3, send_fn3 = sent_texts(monkeypatch, fire_sequence=[make_fire(180, 100)])
    monitor.run_once(conn, send_fn3)
    assert len(calls3) == 0


def test_nws_alert_sent_verbatim_once(conn, place, monkeypatch):
    alert = {
        "id": "urn:oid:redflag-1",
        "event": "Red Flag Warning",
        "headline": "Red Flag Warning issued for Contra Costa County",
        "description": "desc",
        "instruction": "Avoid outdoor burning entirely today.",
        "sent": "2026-10-25T16:00:00-07:00",
        "expires": "2026-10-25T20:00:00-07:00",
        "sender_name": "NWS Bay Area",
        "severity": "Severe",
        "urgency": "Expected",
        "area_desc": "Contra Costa County",
    }
    calls1, send_fn1 = sent_texts(monkeypatch, alert_sequence=[alert])
    monitor.run_once(conn, send_fn1)
    assert len(calls1) == 1
    assert "Avoid outdoor burning entirely today." in calls1[0][1]
    assert "Red Flag Warning issued for Contra Costa County" in calls1[0][1]

    calls2, send_fn2 = sent_texts(monkeypatch, alert_sequence=[alert])
    monitor.run_once(conn, send_fn2)
    assert len(calls2) == 0


def test_nws_alert_outside_watched_events_ignored(conn, place, monkeypatch):
    alert = {
        "id": "urn:oid:smoke-1",
        "event": "Air Quality Alert",
        "headline": "irrelevant",
        "description": "desc",
        "instruction": None,
        "sent": "2026-10-25T16:00:00-07:00",
        "expires": "2026-10-25T20:00:00-07:00",
        "sender_name": "NWS Bay Area",
        "severity": "Minor",
        "urgency": "Future",
        "area_desc": "Contra Costa County",
    }
    calls, send_fn = sent_texts(monkeypatch, alert_sequence=[alert])
    monitor.run_once(conn, send_fn)
    assert len(calls) == 0


def test_due_followup_sends_status_template(conn, place, monkeypatch):
    calls, send_fn = sent_texts(monkeypatch, fire_sequence=[])
    user = conn.execute("SELECT * FROM users WHERE id = ?", (place["user_id"],)).fetchone()
    db.schedule_followup(conn, user["id"], place["id"], "2020-01-01T00:00:00+00:00", "check back")
    monitor.run_once(conn, send_fn)
    assert len(calls) == 1
    assert "Status check for Home" in calls[0][1]
    assert "Wind: from W at 8 mph" in calls[0][1]
    due = db.due_followups(conn)
    assert len(due) == 0


def test_new_fire_alert_shows_local_time_not_utc(conn, place, monkeypatch):
    calls, send_fn = sent_texts(monkeypatch, fire_sequence=[make_fire(40, 0)])
    monitor.run_once(conn, send_fn)
    assert "(UTC)" not in calls[0][1]
    assert "PDT" in calls[0][1] or "PST" in calls[0][1]


def test_official_alert_text_dedupes_identical_headline_and_body(conn, place, monkeypatch):
    alert = {
        "id": "urn:oid:redflag-dup",
        "event": "Red Flag Warning",
        "headline": "Red Flag Warning issued for Contra Costa County",
        "description": "Red Flag Warning issued for Contra Costa County",
        "instruction": "Red Flag Warning issued for Contra Costa County",
        "sent": "2026-10-25T16:00:00-07:00",
        "expires": "2026-10-25T20:00:00-07:00",
        "sender_name": "NWS Bay Area",
        "severity": "Severe",
        "urgency": "Expected",
        "area_desc": "Contra Costa County",
    }
    calls, send_fn = sent_texts(monkeypatch, alert_sequence=[alert])
    monitor.run_once(conn, send_fn)
    assert len(calls) == 1
    assert calls[0][1].count("Red Flag Warning issued for Contra Costa County") == 1
