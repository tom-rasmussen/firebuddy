import time

from firebuddy import config
from firebuddy.sources import http_client, load_fixture

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

_last_nominatim_call = 0.0


class GeocodeError(Exception):
    pass


def _rate_limit_nominatim() -> None:
    global _last_nominatim_call
    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < config.NOMINATIM_MIN_INTERVAL_SEC:
        time.sleep(config.NOMINATIM_MIN_INTERVAL_SEC - elapsed)
    _last_nominatim_call = time.monotonic()


def _geocode_census(client, address: str) -> dict | None:
    r = client.get(
        CENSUS_URL,
        params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
    )
    r.raise_for_status()
    matches = r.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    coords = m["coordinates"]
    return {
        "lat": coords["y"],
        "lon": coords["x"],
        "matched_address": m["matchedAddress"],
        "source": "census",
    }


def _geocode_nominatim(client, address: str) -> dict | None:
    _rate_limit_nominatim()
    r = client.get(
        NOMINATIM_URL,
        params={"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
    )
    r.raise_for_status()
    results = r.json()
    if not results:
        return None
    m = results[0]
    return {
        "lat": float(m["lat"]),
        "lon": float(m["lon"]),
        "matched_address": m["display_name"],
        "source": "nominatim",
    }


def geocode(address: str) -> dict:
    """Resolve an address or place name to lat/lon. Tries Census (street addresses)
    then falls back to Nominatim (towns, landmarks). Raises GeocodeError if neither matches."""
    if config.fixtures_enabled():
        fixtures = load_fixture("geocode.json")
        key = address.strip().lower()
        for fk, fv in fixtures.items():
            if fk.lower() == key or fk.lower() in key:
                return fv
        if "default" in fixtures:
            return fixtures["default"]
        raise GeocodeError(f"No fixture match for address: {address}")

    with http_client() as client:
        result = _geocode_census(client, address)
        if result is None:
            result = _geocode_nominatim(client, address)
        if result is None:
            raise GeocodeError(f"Could not geocode address: {address}")
        return result
