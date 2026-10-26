from firebuddy import config, geo
from firebuddy.sources import TTLCache, http_client, load_fixture

SHELTERS_URL = "https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query"

OUT_FIELDS = (
    "shelter_name,address,city,state,zip,shelter_status,evacuation_capacity,"
    "total_population,pet_accommodations_code,ada_compliant,wheelchair_accessible,org_name"
)

_cache = TTLCache()


def _is_open(status: str | None) -> bool:
    return bool(status) and "open" in status.lower()


def _normalize(attrs: dict, lat: float, lon: float, shelter_lat: float, shelter_lon: float) -> dict:
    distance_mi = geo.haversine_mi(lat, lon, shelter_lat, shelter_lon)
    address_parts = [attrs.get("address"), attrs.get("city"), attrs.get("state"), attrs.get("zip")]
    full_address = ", ".join(p for p in address_parts if p)
    return {
        "name": attrs.get("shelter_name"),
        "address": full_address,
        "distance_mi": round(distance_mi, 1),
        "pets": attrs.get("pet_accommodations_code"),
        "ada": attrs.get("ada_compliant") or attrs.get("wheelchair_accessible"),
        "org": attrs.get("org_name"),
        "status": attrs.get("shelter_status"),
    }


def find_shelters(lat: float, lon: float, max_results: int = 3) -> list[dict]:
    """Open FEMA National Shelter System shelters within 50 mi, nearest first."""
    if config.fixtures_enabled():
        data = load_fixture("shelters.json")
        shelters = []
        for feat in data.get("features", []):
            attrs = feat["attributes"]
            geom = feat["geometry"]
            if _is_open(attrs.get("shelter_status")):
                shelters.append(_normalize(attrs, lat, lon, geom["y"], geom["x"]))
        shelters.sort(key=lambda s: s["distance_mi"])
        return shelters[:max_results]

    cache_key = f"{round(lat, 3)},{round(lon, 3)}"
    cached = _cache.get(cache_key)
    if cached is None:
        with http_client() as client:
            r = client.get(
                SHELTERS_URL,
                params={
                    "where": "1=1",
                    "geometry": f"{lon},{lat}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                    "distance": 50,
                    "units": "esriSRUnit_StatuteMile",
                    "outFields": OUT_FIELDS,
                    "outSR": 4326,
                    "f": "json",
                },
            )
            r.raise_for_status()
            cached = r.json().get("features", [])
            _cache.set(cache_key, cached)

    shelters = []
    for feat in cached:
        attrs = feat["attributes"]
        geom = feat["geometry"]
        if _is_open(attrs.get("shelter_status")):
            shelters.append(_normalize(attrs, lat, lon, geom["y"], geom["x"]))
    shelters.sort(key=lambda s: s["distance_mi"])
    return shelters[:max_results]
