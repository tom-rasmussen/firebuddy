import math

import pytest

from firebuddy import geo


def test_haversine_zero_distance():
    assert geo.haversine_mi(37.8, -122.0, 37.8, -122.0) == pytest.approx(0, abs=1e-6)


def test_haversine_known_distance():
    # San Francisco to Los Angeles, ~347 statute miles great-circle.
    d = geo.haversine_mi(37.7749, -122.4194, 34.0522, -118.2437)
    assert d == pytest.approx(347, abs=5)


def test_bearing_due_east():
    b = geo.bearing_deg(37.8, -122.0, 37.8, -121.0)
    assert b == pytest.approx(90, abs=1)


def test_bearing_due_north():
    b = geo.bearing_deg(37.0, -122.0, 38.0, -122.0)
    assert b == pytest.approx(0, abs=1)


def test_bearing_due_south():
    b = geo.bearing_deg(38.0, -122.0, 37.0, -122.0)
    assert b == pytest.approx(180, abs=1)


def test_bearing_due_west():
    b = geo.bearing_deg(37.8, -121.0, 37.8, -122.0)
    assert b == pytest.approx(270, abs=1)


@pytest.mark.parametrize(
    "deg,expected",
    [
        (0, "N"), (22.5, "NNE"), (45, "NE"), (67.5, "ENE"),
        (90, "E"), (112.5, "ESE"), (135, "SE"), (157.5, "SSE"),
        (180, "S"), (202.5, "SSW"), (225, "SW"), (247.5, "WSW"),
        (270, "W"), (292.5, "WNW"), (315, "NW"), (337.5, "NNW"),
        (359, "N"), (361, "N"),
    ],
)
def test_compass_16(deg, expected):
    assert geo.compass_16(deg) == expected


def test_angular_diff_zero():
    assert geo.angular_diff(90, 90) == 0


def test_angular_diff_simple():
    assert geo.angular_diff(10, 50) == 40


def test_angular_diff_wraps_around_north():
    assert geo.angular_diff(350, 10) == 20


def test_angular_diff_max_180():
    assert geo.angular_diff(0, 180) == 180


def test_angular_diff_is_symmetric():
    assert geo.angular_diff(30, 200) == geo.angular_diff(200, 30)


def test_bearing_antimeridian_safe():
    b = geo.bearing_deg(0, 179, 0, -179)
    assert 0 <= b < 360
    assert not math.isnan(b)
