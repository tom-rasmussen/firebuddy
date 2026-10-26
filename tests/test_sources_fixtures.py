import pytest

from firebuddy import config
from firebuddy.sources import fires, geocode, nws, shelters

HOME_LAT, HOME_LON = 37.8216, -122.0001


@pytest.fixture(autouse=True)
def use_fixtures(monkeypatch):
    monkeypatch.setattr(config, "FIREBUDDY_FIXTURES", "fixtures")


def test_geocode_fixture_match():
    result = geocode.geocode("123 Main St, Danville, CA")
    assert result["lat"] == pytest.approx(37.8216)
    assert result["lon"] == pytest.approx(-122.0001)
    assert "Danville" in result["matched_address"]


def test_fires_near_fixture():
    incidents = fires.fires_near(HOME_LAT, HOME_LON, 15)
    assert len(incidents) == 1
    fire = incidents[0]
    assert fire["name"] == "Morgan Fire"
    assert fire["acres"] == 40
    assert fire["direction"] == "E"
    assert fire["distance_mi"] == pytest.approx(9, abs=1)


def test_official_alerts_fixture_verbatim():
    alerts = nws.official_alerts(HOME_LAT, HOME_LON)
    assert len(alerts) == 1
    assert alerts[0]["event"] == "Red Flag Warning"
    assert "Extreme caution" in alerts[0]["instruction"]


def test_wind_data_fixture():
    wind = nws.wind_data(HOME_LAT, HOME_LON)
    assert wind["station_id"] == "KCCR"
    assert wind["wind_from_deg"] == 90
    assert wind["wind_speed_mph"] == pytest.approx(22.5 * 0.621371, abs=0.1)
    assert len(wind["forecast_hourly"]) == 6


def test_find_shelters_fixture_filters_closed():
    result = shelters.find_shelters(HOME_LAT, HOME_LON, max_results=3)
    assert len(result) == 1
    assert result[0]["name"] == "Monte Vista HS Gym"


def test_get_timezone_fixture_mode_returns_default():
    assert nws.get_timezone(HOME_LAT, HOME_LON) == nws.DEFAULT_TIMEZONE
