from datetime import datetime, timezone

from firebuddy import config, geo
from firebuddy.sources import TTLCache, http_client, load_fixture

WFIGS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Incident_Locations_Current/FeatureServer/0/query"
)

OUT_FIELDS = (
    "IncidentName,IncidentSize,PercentContained,FireDiscoveryDateTime,"
    "ModifiedOnDateTime_dt,UniqueFireIdentifier,IrwinID,POOState,POOCounty,"
    "IncidentTypeCategory"
)

_cache = TTLCache()


def _epoch_ms_to_iso(ms) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _normalize(attrs: dict, place_lat: float, place_lon: float, fire_lat: float, fire_lon: float) -> dict:
    distance_mi = geo.haversine_mi(place_lat, place_lon, fire_lat, fire_lon)
    bearing = geo.bearing_deg(place_lat, place_lon, fire_lat, fire_lon)
    return {
        "key": attrs.get("IrwinID") or attrs.get("UniqueFireIdentifier"),
        "name": attrs.get("IncidentName"),
        "acres": attrs.get("IncidentSize"),
        "percent_contained": attrs.get("PercentContained"),
        "distance_mi": round(distance_mi, 1),
        "direction": geo.compass_16(bearing),
        "bearing_deg": round(bearing, 1),
        "discovered": _epoch_ms_to_iso(attrs.get("FireDiscoveryDateTime")),
        "updated": _epoch_ms_to_iso(attrs.get("ModifiedOnDateTime_dt")),
        "source": "NIFC",
    }


def fires_near(lat: float, lon: float, radius_mi: float) -> list[dict]:
    """Active wildfire incidents (IncidentTypeCategory='WF') within radius_mi of lat/lon."""
    if config.fixtures_enabled():
        data = load_fixture("fires.json")
        out = []
        for feat in data.get("features", []):
            attrs = feat["attributes"]
            geom = feat["geometry"]
            out.append(_normalize(attrs, lat, lon, geom["y"], geom["x"]))
        return out

    cache_key = f"{round(lat, 3)},{round(lon, 3)},{radius_mi}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    with http_client() as client:
        r = client.get(
            WFIGS_URL,
            params={
                "where": "IncidentTypeCategory='WF'",
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": radius_mi,
                "units": "esriSRUnit_StatuteMile",
                "outFields": OUT_FIELDS,
                "outSR": 4326,
                "f": "json",
            },
        )
        r.raise_for_status()
        features = r.json().get("features", [])
        out = []
        for feat in features:
            attrs = feat["attributes"]
            geom = feat["geometry"]
            out.append(_normalize(attrs, lat, lon, geom["y"], geom["x"]))
        _cache.set(cache_key, out)
        return out
