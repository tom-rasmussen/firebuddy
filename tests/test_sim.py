import importlib

import pytest

import sim
from firebuddy import clock


@pytest.fixture(autouse=True)
def reset_world():
    sim.WORLD["fires"].clear()
    sim.WORLD["alerts"].clear()
    sim.WORLD["wind"] = None
    sim.WORLD["shelters"].clear()
    clock.set_override(None)
    yield
    sim.WORLD["fires"].clear()
    sim.WORLD["alerts"].clear()
    sim.WORLD["wind"] = None
    sim.WORLD["shelters"].clear()
    clock.set_override(None)


def test_cmd_fire_sets_bearing_from_compass():
    sim.cmd_fire(["Morgan", "40", "9", "E"])
    fire = sim.WORLD["fires"]["Morgan"]
    assert fire["acres"] == 40
    assert fire["distance_mi"] == 9
    assert fire["bearing_deg"] == 90.0


def test_cmd_grow_updates_existing_fire():
    sim.cmd_fire(["Morgan", "40", "9", "E"])
    sim.cmd_grow(["Morgan", "150"])
    assert sim.WORLD["fires"]["Morgan"]["acres"] == 150


def test_cmd_contain_updates_percent():
    sim.cmd_fire(["Morgan", "40", "9", "E"])
    sim.cmd_contain(["Morgan", "100"])
    assert sim.WORLD["fires"]["Morgan"]["percent_contained"] == 100


def test_cmd_nws_adds_alert_via_alias():
    sim.cmd_nws(["redflag", "windy", "today"])
    assert "Red Flag Warning" in sim.WORLD["alerts"]
    assert sim.WORLD["alerts"]["Red Flag Warning"]["headline"] == "windy today"


def test_cmd_wind_sets_observation():
    sim.cmd_wind(["90", "14", "25"])
    assert sim.WORLD["wind"]["wind_from_deg"] == 90.0
    assert sim.WORLD["wind"]["wind_gust_mph"] == 25.0


def test_cmd_shelter_adds_open_shelter_with_multiword_name():
    sim.cmd_shelter(["Monte", "Vista", "open"])
    assert sim.WORLD["shelters"][0]["name"] == "Monte Vista"
    assert sim.WORLD["shelters"][0]["status"] == "open"


def test_fake_fires_near_filters_by_radius():
    sim.cmd_fire(["Morgan", "40", "9", "E"])
    sim.cmd_fire(["Far", "10", "40", "W"])
    assert [f["name"] for f in sim._fake_fires_near(0, 0, 15)] == ["Morgan"]


def test_fake_find_shelters_filters_closed():
    sim.cmd_shelter(["Open One", "open"])
    sim.cmd_shelter(["Closed One", "closed"])
    result = sim._fake_find_shelters(0, 0)
    assert [s["name"] for s in result] == ["Open One"]


def test_module_imports_cleanly():
    importlib.reload(sim)
