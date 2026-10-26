import pytest

from firebuddy import config
from firebuddy.sources import TTLCache
from firebuddy.sources import nws as nws_module


@pytest.fixture(autouse=True)
def live_mode_and_fresh_cache(monkeypatch):
    monkeypatch.setattr(config, "FIREBUDDY_FIXTURES", "")
    monkeypatch.setattr(nws_module, "_points_cache", TTLCache())


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, calls, payload):
        self._calls = calls
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        self._calls.append(url)
        return _FakeResponse(self._payload)


def test_get_timezone_returns_point_timezone_and_caches(monkeypatch):
    calls = []
    payload = {
        "properties": {
            "forecastHourly": "https://api.weather.gov/gridpoints/X/1,2/forecast/hourly",
            "observationStations": "https://api.weather.gov/gridpoints/X/1,2/stations",
            "timeZone": "America/New_York",
        }
    }
    monkeypatch.setattr(nws_module, "http_client", lambda timeout=15.0: _FakeClient(calls, payload))

    tz = nws_module.get_timezone(40.7, -74.0)
    assert tz == "America/New_York"
    assert len(calls) == 1

    tz_again = nws_module.get_timezone(40.7, -74.0)
    assert tz_again == "America/New_York"
    assert len(calls) == 1  # cached, no second HTTP call


def test_get_timezone_falls_back_when_field_missing(monkeypatch):
    calls = []
    payload = {
        "properties": {
            "forecastHourly": "https://api.weather.gov/gridpoints/X/1,2/forecast/hourly",
            "observationStations": "https://api.weather.gov/gridpoints/X/1,2/stations",
        }
    }
    monkeypatch.setattr(nws_module, "http_client", lambda timeout=15.0: _FakeClient(calls, payload))
    assert nws_module.get_timezone(10.0, 20.0) == nws_module.DEFAULT_TIMEZONE


def test_get_timezone_falls_back_on_request_failure(monkeypatch):
    def boom(timeout=15.0):
        raise RuntimeError("network down")

    monkeypatch.setattr(nws_module, "http_client", boom)
    assert nws_module.get_timezone(1.0, 2.0) == nws_module.DEFAULT_TIMEZONE
