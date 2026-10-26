import math

EARTH_RADIUS_MI = 3958.8

COMPASS_POINTS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.asin(min(1, math.sqrt(a)))
    return EARTH_RADIUS_MI * c


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing in degrees [0, 360) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    theta = math.atan2(x, y)
    return (math.degrees(theta) + 360) % 360


def compass_16(deg: float) -> str:
    """Nearest 16-point compass label for a bearing in degrees."""
    idx = round((deg % 360) / 22.5) % 16
    return COMPASS_POINTS[idx]


def angular_diff(a_deg: float, b_deg: float) -> float:
    """Smallest absolute angular difference between two bearings, in [0, 180]."""
    diff = abs(a_deg - b_deg) % 360
    return 360 - diff if diff > 180 else diff
