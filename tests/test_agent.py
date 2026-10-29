import json

import pytest

from firebuddy import agent, config, db
from firebuddy.sources import geocode

HOME_LAT, HOME_LON = 37.8216, -122.0001


@pytest.fixture(autouse=True)
def use_fixtures(monkeypatch):
    monkeypatch.setattr(config, "FIREBUDDY_FIXTURES", "fixtures")


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def user(conn):
    return db.get_or_create_user(conn, "+15550009999")


@pytest.fixture
def place(conn, user):
    return db.add_place(conn, user["id"], "Home", "123 Main St, Danville, CA", HOME_LAT, HOME_LON, 15)


def text_msg(text, in_tokens=10, out_tokens=5):
    return agent.FakeMessage(
        content=[agent.TextBlock(text=text)], stop_reason="end_turn", usage=agent.Usage(in_tokens, out_tokens)
    )


def tool_msg(name, tool_input, call_id="t1", in_tokens=10, out_tokens=5):
    return agent.FakeMessage(
        content=[agent.ToolUseBlock(id=call_id, name=name, input=tool_input)],
        stop_reason="tool_use",
        usage=agent.Usage(in_tokens, out_tokens),
    )


# --- tool implementations ---

def test_tool_assess_situation_fixture_get_ready(conn, user, place):
    result = agent.execute_tool(conn, user["id"], "assess_situation", {"place_id": place["id"]})
    assert result["level"] == "GET READY: LEAVE EARLY IF YOU NEED TIME"
    assert result["place_label"] == "Home"


def test_tool_wind_check_fixture_toward(conn, user, place):
    result = agent.execute_tool(conn, user["id"], "wind_check", {"place_id": place["id"]})
    assert result["relation_to_fire"] == "toward"
    assert result["relative_to_fire"] == "Morgan Fire"


def test_tool_find_shelters_fixture_filters_closed(conn, user, place):
    result = agent.execute_tool(conn, user["id"], "find_shelters", {"place_id": place["id"]})
    assert len(result["shelters"]) == 1
    assert result["shelters"][0]["name"] == "Monte Vista HS Gym"


def test_tool_remove_place_rejects_other_users_place(conn, user, place):
    other_user = db.get_or_create_user(conn, "+15551112222")
    result = agent.execute_tool(conn, other_user["id"], "remove_place", {"place_id": place["id"]})
    assert result == {"error": "Place not found."}
    assert db.get_place(conn, place["id"])["active"] == 1


def test_tool_set_radius_clamps_range(conn, user, place):
    agent.execute_tool(conn, user["id"], "set_radius", {"place_id": place["id"], "radius_mi": 999})
    assert db.get_place(conn, place["id"])["radius_mi"] == 50
    agent.execute_tool(conn, user["id"], "set_radius", {"place_id": place["id"], "radius_mi": 0})
    assert db.get_place(conn, place["id"])["radius_mi"] == 1


def test_tool_schedule_followup_clamps_hours(conn, user, place):
    result = agent.execute_tool(
        conn, user["id"], "schedule_followup", {"place_id": place["id"], "hours": 100, "note": "check"}
    )
    assert result["hours"] == 24
    result = agent.execute_tool(
        conn, user["id"], "schedule_followup", {"place_id": place["id"], "hours": 0.1, "note": "check"}
    )
    assert result["hours"] == 0.5


def test_tool_add_place_success(conn, user, place):
    result = agent.execute_tool(
        conn, user["id"], "add_place", {"address": "500 Diablo Rd, Danville, CA", "label": "Parents"}
    )
    assert result["label"] == "Parents"
    assert result["radius_mi"] == 15
    places = db.list_places(conn, user["id"])
    assert len(places) == 2
    assert {p["label"] for p in places} == {"Home", "Parents"}


def test_tool_add_place_geocode_error(conn, user, monkeypatch):
    def boom(address):
        raise geocode.GeocodeError("nope")

    monkeypatch.setattr(agent.geocode, "geocode", boom)
    result = agent.execute_tool(conn, user["id"], "add_place", {"address": "nowhere"})
    assert "error" in result


def test_execute_tool_unknown_name(conn, user):
    result = agent.execute_tool(conn, user["id"], "nonexistent_tool", {})
    assert "error" in result


# --- grounding validator ---

def test_validate_grounded_numbers_pass():
    blob = json.dumps({"distance_mi": 9.0, "acres": 40})
    result = agent.validate("The fire is 9 mi away and 40 acres.", blob, "")
    assert result.ok


def test_validate_ungrounded_number_fails():
    result = agent.validate("The fire is 99999 acres.", "{}", "")
    assert not result.ok
    assert "99999" in result.reason


def test_validate_ignores_clock_times():
    result = agent.validate("Alert sent at 4:30 PM today.", "{}", "")
    assert result.ok


def test_validate_blocked_phrase_unquoted_fails():
    result = agent.validate("You're safe for now.", "{}", "")
    assert not result.ok
    assert "blocked phrase" in result.reason


def test_validate_blocked_phrase_quoted_in_tool_result_passes():
    blob = "Shelter order text: Stay inside, you can stay until further notice."
    result = agent.validate("Stay inside, you can stay until further notice.", blob, "")
    assert result.ok


def test_validate_unquoted_route_instruction_fails():
    result = agent.validate("Take Highway 24 to escape.", "{}", "")
    assert not result.ok


def test_validate_911_and_211_are_exempt_from_grounding():
    text = (
        "MONITOR. If you're in immediate danger, call 911. If you feel unsafe, leave. "
        "You don't need to wait for an order. Call 211 for shelter info."
    )
    result = agent.validate(text, "{}", "")
    assert result.ok


def test_validate_empty_reply_fails():
    result = agent.validate("   ", "{}", "")
    assert not result.ok


# --- run_turn ---

def test_run_turn_tool_then_grounded_text(conn, user, place):
    llm = agent.FakeLLMClient(
        [
            tool_msg("assess_situation", {"place_id": place["id"]}),
            text_msg("GET READY. Morgan Fire is 9.0 mi E. Red Flag Warning in effect."),
        ]
    )
    reply = agent.run_turn(conn, user, "should I leave?", llm)
    assert "GET READY" in reply
    trace = db.last_traces(conn, 1)[0]
    assert trace["validator_result"].startswith("ok")
    assert trace["retries"] == 0
    assert len(json.loads(trace["tool_calls"])) == 1


def test_run_turn_handles_thinking_blocks_alongside_tool_use(conn, user, place):
    # claude-sonnet-5-5 (extended thinking) returns a ThinkingBlock alongside tool_use;
    # it must round-trip into the next assistant message without crashing.
    llm = agent.FakeLLMClient(
        [
            agent.FakeMessage(
                content=[
                    agent.ThinkingBlock(),
                    agent.ToolUseBlock(id="t1", name="assess_situation", input={"place_id": place["id"]}),
                ],
                stop_reason="tool_use",
            ),
            agent.FakeMessage(
                content=[agent.ThinkingBlock(), agent.TextBlock(text="GET READY. 9.0 mi E.")],
                stop_reason="end_turn",
            ),
        ]
    )
    reply = agent.run_turn(conn, user, "should I leave?", llm)
    assert "GET READY" in reply
    # the thinking block must have round-tripped into the follow-up request's messages
    assert any(
        isinstance(c, dict) and c.get("type") == "thinking"
        for call in llm.calls
        for msg in call["messages"]
        if isinstance(msg.get("content"), list)
        for c in msg["content"]
    )


def test_run_turn_grounding_retry_recovers(conn, user, place):
    llm = agent.FakeLLMClient(
        [
            tool_msg("assess_situation", {"place_id": place["id"]}),
            text_msg("The fire is 987654 acres, huge!"),  # ungrounded hallucination
            text_msg("It's 40 acres, 0% contained."),  # grounded correction
        ]
    )
    reply = agent.run_turn(conn, user, "how big is the fire?", llm)
    assert reply == "It's 40 acres, 0% contained."
    trace = db.last_traces(conn, 1)[0]
    assert trace["retries"] == 1
    assert trace["validator_result"].startswith("ok")
    assert "first attempt: ungrounded number: 987654" in trace["validator_result"]


def test_run_turn_double_failure_falls_back(conn, user, place):
    llm = agent.FakeLLMClient(
        [
            tool_msg("assess_situation", {"place_id": place["id"]}),
            text_msg("The fire is 987654 acres!"),
            text_msg("Actually it's 123456 acres!"),  # still ungrounded
        ]
    )
    reply = agent.run_turn(conn, user, "how big is the fire?", llm)
    assert "couldn't verify a full answer" in reply
    trace = db.last_traces(conn, 1)[0]
    assert trace["retries"] == 1
    assert trace["validator_result"].startswith("failed: ungrounded number: 123456")
    assert "first attempt: ungrounded number: 987654" in trace["validator_result"]


def test_run_turn_numbers_from_earlier_user_messages_are_grounded(conn, user, place):
    db.log_message(conn, user["id"], "in", "3301 Camino Tassajara, Danville, CA")
    llm = agent.FakeLLMClient(
        [
            tool_msg("assess_situation", {"place_id": place["id"]}),
            text_msg("The address you sent, 3301 Camino Tassajara, is 9.0 mi from Morgan Fire."),
        ]
    )
    reply = agent.run_turn(conn, user, "is the wind blowing the fire toward me?", llm)
    assert "3301" in reply
    assert db.last_traces(conn, 1)[0]["retries"] == 0


def test_run_turn_numbers_from_earlier_bot_replies_are_not_grounded(conn, user, place):
    db.log_message(conn, user["id"], "out", "Morgan Fire grew to 777777 acres.")
    llm = agent.FakeLLMClient(
        [
            tool_msg("assess_situation", {"place_id": place["id"]}),
            text_msg("Morgan Fire is 777777 acres."),
            text_msg("Morgan Fire is 9.0 mi E."),
        ]
    )
    agent.run_turn(conn, user, "how big is it?", llm)
    assert db.last_traces(conn, 1)[0]["retries"] == 1


def test_run_turn_caps_tool_iterations(conn, user, place):
    responses = [tool_msg("list_places", {}, call_id=f"t{i}") for i in range(7)]
    responses.append(text_msg("Here's what I found."))
    llm = agent.FakeLLMClient(responses)
    reply = agent.run_turn(conn, user, "list my places please", llm)
    assert reply == "Here's what I found."
    trace = db.last_traces(conn, 1)[0]
    assert len(json.loads(trace["tool_calls"])) == 6
    assert trace["retries"] == 1  # the capped tool_use response produced empty text first
