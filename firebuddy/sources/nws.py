from firebuddy import config, geo
from firebuddy.sources import TTLCache, http_client, load_fixture

ALERTS_URL = "https://api.weather.gov/alerts/active"
POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"

KMH_TO_MPH = 0.621371

_points_cache = TTLCache()
_alerts_cache = TTLCache()
_obs_cache = TTLCache()
_forecast_cache = TTLCache()


def official_alerts(lat: float, lon: float) -> list[dict]:
    """Active NWS alerts whose polygon covers (lat, lon)."""
    if config.fixtures_enabled():
        data = load_fixture("nws_alerts.json")
        return [_normalize_alert(f["properties"]) for f in data.get("features", [])]

    cache_key = f"{round(lat, 4)},{round(lon, 4)}"
    cached = _alerts_cache.get(cache_key)
    if cached is not None:
        return cached

    with http_client() as client:
        r = client.get(ALERTS_URL, params={"point": f"{round(lat, 4)},{round(lon, 4)}"})
        r.raise_for_status()
        features = r.json().get("features", [])
        out = [_normalize_alert(f["properties"]) for f in features]
        _alerts_cache.set(cache_key, out)
        return out


def _normalize_alert(props: dict) -> dict:
    return {
        "id": props.get("id"),
        "event": props.get("event"),
        "headline": props.get("headline"),
        "description": props.get("description"),
        "instruction": props.get("instruction"),
        "sent": props.get("sent"),
        "expires": props.get("expires"),
        "sender_name": props.get("senderName"),
        "severity": props.get("severity"),
        "urgency": props.get("urgency"),
        "area_desc": props.get("areaDesc"),
    }


def _get_points(client, lat: float, lon: float) -> dict:
    cache_key = f"{round(lat, 4)},{round(lon, 4)}"
    cached = _points_cache.get(cache_key)
    if cached is not None:
        return cached
    r = client.get(POINTS_URL.format(lat=round(lat, 4), lon=round(lon, 4)))
    r.raise_for_status()
    props = r.json()["properties"]
    result = {
        "forecast_hourly_url": props["forecastHourly"],
        "observation_stations_url": props["observationStations"],
    }
    _points_cache.set(cache_key, result)
    return result


def _nearest_station(client, observation_stations_url: str, lat: float, lon: float) -> dict:
    cached = _obs_cache.get(observation_stations_url)
    if cached is None:
        r = client.get(observation_stations_url)
        r.raise_for_status()
        features = r.json()["features"]
        cached = features
        _obs_cache.set(observation_stations_url, cached)
    first = cached[0]
    station_id = first["properties"]["stationIdentifier"]
    station_lon, station_lat = first["geometry"]["coordinates"][0], first["geometry"]["coordinates"][1]
    distance_mi = geo.haversine_mi(lat, lon, station_lat, station_lon)
    return {"station_id": station_id, "distance_mi": round(distance_mi, 1)}


def wind_data(lat: float, lon: float) -> dict:
    """Current wind observation (nearest station) plus next-12h hourly forecast."""
    if config.fixtures_enabled():
        obs = load_fixture("nws_observation.json")["properties"]
        forecast = load_fixture("nws_forecast.json")["properties"]["periods"][:12]
        station = load_fixture("nws_station.json")
        station_lon, station_lat = station["geometry"]["coordinates"][0], station["geometry"]["coordinates"][1]
        distance_mi = geo.haversine_mi(lat, lon, station_lat, station_lon)
        return _build_wind_result(obs, forecast, station["properties"]["stationIdentifier"], round(distance_mi, 1))

    with http_client() as client:
        points = _get_points(client, lat, lon)
        station = _nearest_station(client, points["observation_stations_url"], lat, lon)

        obs_cache_key = station["station_id"]
        obs = _obs_cache.get(f"latest:{obs_cache_key}")
        if obs is None:
            r = client.get(f"https://api.weather.gov/stations/{station['station_id']}/observations/latest")
            r.raise_for_status()
            obs = r.json()["properties"]
            _obs_cache.set(f"latest:{obs_cache_key}", obs)

        forecast = _forecast_cache.get(points["forecast_hourly_url"])
        if forecast is None:
            r = client.get(points["forecast_hourly_url"])
            r.raise_for_status()
            forecast = r.json()["properties"]["periods"][:12]
            _forecast_cache.set(points["forecast_hourly_url"], forecast)

        return _build_wind_result(obs, forecast, station["station_id"], station["distance_mi"])


def _build_wind_result(obs: dict, forecast: list[dict], station_id: str, station_distance_mi: float) -> dict:
    speed_kmh = (obs.get("windSpeed") or {}).get("value")
    gust_kmh = (obs.get("windGust") or {}).get("value")
    direction_deg = (obs.get("windDirection") or {}).get("value")
    return {
        "station_id": station_id,
        "station_distance_mi": station_distance_mi,
        "obs_time": obs.get("timestamp"),
        "wind_from_deg": direction_deg,
        "wind_speed_mph": round(speed_kmh * KMH_TO_MPH, 1) if speed_kmh is not None else None,
        "wind_gust_mph": round(gust_kmh * KMH_TO_MPH, 1) if gust_kmh is not None else None,
        "forecast_hourly": [
            {
                "start_time": p.get("startTime"),
                "wind_speed": p.get("windSpeed"),
                "wind_direction": p.get("windDirection"),
            }
            for p in forecast
        ],
    }
