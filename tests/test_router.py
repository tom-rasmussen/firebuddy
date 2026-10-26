import pytest

from firebuddy import agent, config, db, router, templates

HOME_LAT, HOME_LON = 37.8216, -122.0001


@pytest.fixture(autouse=True)
def use_fixtures(monkeypatch):
    monkeypatch.setattr(config, "FIREBUDDY_FIXTURES", "fixtures")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


# --- parse_command ---

@pytest.mark.parametrize(
    "text,expected",
    [
        ("ADD 123 Main St", ("ADD", "123 Main St")),
        ("add 123 main st", ("ADD", "123 main st")),
        ("LIST", ("LIST", None)),
        ("list", ("LIST", None)),
        ("REMOVE 2", ("REMOVE", 2)),
        ("RADIUS 20", ("RADIUS", (20.0, 1))),
        ("RADIUS 20 place 2", ("RADIUS", (20.0, 2))),
        ("STATUS", ("STATUS", None)),
        ("STOP", ("STOP", None)),
        ("START", ("START", None)),
        ("HELP", ("HELP", None)),
        ("should I leave?", None),
        ("hi", None),
    ],
)
def test_parse_command(text, expected):
    assert router.parse_command(text) == expected


# --- onboarding ---

def test_onboarding_greets_brand_new_user(conn):
    reply = router.route_message(conn, "+15551110000", "hi")
    assert reply == templates.ONBOARDING_GREETING
    user = db.get_or_create_user(conn, "+15551110000")
    assert user["state"] == "awaiting_address"


def test_onboarding_address_adds_place_and_confirms(conn):
    router.route_message(conn, "+15551110000", "hi")
    reply = router.route_message(conn, "+15551110000", "123 Main St, Danville, CA")
    assert "Watching" in reply
    assert "15 mi radius" in reply
    user = db.get_or_create_user(conn, "+15551110000")
    assert user["state"] is None
    places = db.list_places(conn, user["id"])
    assert len(places) == 1
    assert places[0]["label"] == "Home"


# --- deterministic commands ---

def test_add_list_remove_radius_roundtrip(conn):
    phone = "+15551110001"
    r1 = router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    assert "Added" in r1

    r2 = router.route_message(conn, phone, "LIST")
    assert "1. Home" in r2 or "1." in r2

    r3 = router.route_message(conn, phone, "RADIUS 25")
    assert "25 mi" in r3

    r4 = router.route_message(conn, phone, "REMOVE 1")
    assert "Removed" in r4

    r5 = router.route_message(conn, phone, "LIST")
    assert r5 == templates.NO_PLACES_TEXT


def test_remove_out_of_range(conn):
    phone = "+15551110002"
    router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    reply = router.route_message(conn, phone, "REMOVE 5")
    assert "No place #5" in reply


def test_status_uses_fixture_data(conn):
    phone = "+15551110003"
    router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    reply = router.route_message(conn, phone, "STATUS")
    assert "Morgan Fire" in reply


def test_status_includes_wind_line(conn):
    phone = "+15551110009"
    router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    reply = router.route_message(conn, phone, "STATUS")
    assert "Wind:" in reply
    assert "blowing from Morgan Fire toward you" in reply


def test_help_lists_commands(conn):
    reply = router.route_message(conn, "+15551110004", "HELP")
    assert "ADD <address>" in reply


def test_stop_then_freeform_ignored_but_commands_still_work(conn):
    phone = "+15551110005"
    router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    stop_reply = router.route_message(conn, phone, "STOP")
    assert stop_reply == templates.STOPPED_TEXT

    ignored = router.route_message(conn, phone, "should I leave?")
    assert ignored is None

    still_works = router.route_message(conn, phone, "LIST")
    assert "Home" in still_works

    start_reply = router.route_message(conn, phone, "START")
    assert start_reply == templates.STARTED_TEXT


def test_freeform_without_api_key_returns_fallback(conn):
    phone = "+15551110006"
    router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    reply = router.route_message(conn, phone, "should I leave?")
    assert reply == templates.AGENT_UNAVAILABLE_TEXT


def test_freeform_with_explicit_fake_llm_client(conn):
    phone = "+15551110007"
    router.route_message(conn, phone, "ADD 123 Main St, Danville, CA")
    llm = agent.FakeLLMClient(
        [agent.FakeMessage(content=[agent.TextBlock(text="You're all clear for now.")], stop_reason="end_turn")]
    )
    reply = router.route_message(conn, phone, "anything happening?", llm)
    assert reply == "You're all clear for now."


def test_add_place_bad_address_asks_for_clarification(conn, monkeypatch):
    phone = "+15551110008"
    monkeypatch.setattr(config, "FIREBUDDY_FIXTURES", "")

    def boom(address):
        from firebuddy.sources.geocode import GeocodeError

        raise GeocodeError("nope")

    monkeypatch.setattr(router.geocode, "geocode", boom)
    reply = router.route_message(conn, phone, "ADD somewhere vague")
    assert "couldn't find" in reply
