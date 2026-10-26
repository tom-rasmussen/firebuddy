import pytest

from evals.runner import TurnBudget, TurnBudgetExceeded, run_all, run_scenario
from evals.scenarios import SCENARIOS
from firebuddy import agent


def test_all_scenarios_well_formed():
    assert len(SCENARIOS) >= 10
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)), "scenario ids must be unique"
    for s in SCENARIOS:
        assert s["title"]
        assert s["turns"] and all(isinstance(t, str) for t in s["turns"])
        assert callable(s["check"])
        assert set(s["world"].keys()) == {"fires", "alerts", "wind", "shelters"}


def _scripted_client_factory(*response_lists):
    """Returns a factory that hands out one FakeLLMClient per call, in order."""
    iterator = iter(response_lists)

    def factory():
        return agent.FakeLLMClient(next(iterator))

    return factory


def _tool_then_text(tool_name, tool_input, text):
    return [
        agent.FakeMessage(
            content=[agent.ToolUseBlock(id="t1", name=tool_name, input=tool_input)], stop_reason="tool_use"
        ),
        agent.FakeMessage(content=[agent.TextBlock(text=text)], stop_reason="end_turn"),
    ]


def test_run_scenario_no_fires_monitor_passes():
    scenario = next(s for s in SCENARIOS if s["id"] == "no_fires_monitor")
    place_id = 1  # the runner always creates the first (only) place with id 1
    responses = _tool_then_text(
        "assess_situation",
        {"place_id": place_id},
        "MONITOR: nothing nearby right now. If you're in immediate danger, call 911. "
        "If you feel unsafe, leave. You don't need to wait for an order.",
    )
    budget = TurnBudget(60)
    result = run_scenario(scenario, _scripted_client_factory(responses), budget)
    assert result["passed"], result["reason"]
    assert budget.spent == 1


def test_run_scenario_evacuation_immediate_verbatim_passes():
    scenario = next(s for s in SCENARIOS if s["id"] == "evacuation_immediate_leave_now_verbatim")
    place_id = 1
    text = (
        "LEAVE NOW. Evacuate immediately via Highway 4 westbound. Do not delay. "
        "If you're in immediate danger, call 911. If you feel unsafe, leave. You don't need to wait for an order."
    )
    responses = _tool_then_text("assess_situation", {"place_id": place_id}, text)
    budget = TurnBudget(60)
    result = run_scenario(scenario, _scripted_client_factory(responses), budget)
    assert result["passed"], result["reason"]


def test_run_scenario_fails_when_reply_violates_the_scenario():
    scenario = next(s for s in SCENARIOS if s["id"] == "no_fires_monitor")
    place_id = 1
    # The world is genuinely empty, so the real assess_situation tool still (correctly)
    # returns MONITOR -- but the reply's "leave now" wording should fail this scenario's
    # check() even though the deterministic level itself matched.
    responses = _tool_then_text(
        "assess_situation",
        {"place_id": place_id},
        "GET READY. Leave now if you have kids or pets. Call 911 if unsafe.",
    )
    budget = TurnBudget(60)
    result = run_scenario(scenario, _scripted_client_factory(responses), budget)
    assert not result["passed"]
    assert "leave now" in result["reason"]


def test_run_scenario_watch_and_followup():
    scenario = next(s for s in SCENARIOS if s["id"] == "watch_and_followup")
    responses = [
        agent.FakeMessage(
            content=[agent.ToolUseBlock(id="t1", name="add_place",
                                         input={"address": "500 Diablo Rd, Danville, CA", "label": "Parents"})],
            stop_reason="tool_use",
        ),
        agent.FakeMessage(
            content=[agent.ToolUseBlock(id="t2", name="schedule_followup",
                                         input={"place_id": 2, "hours": 2, "note": "check back"})],
            stop_reason="tool_use",
        ),
        agent.FakeMessage(
            content=[agent.TextBlock(
                text="Added Parents at 500 Diablo Rd, Danville, CA. I'll check back in 2 hours. "
                     "Call 911 if you're in immediate danger."
            )],
            stop_reason="end_turn",
        ),
    ]
    budget = TurnBudget(60)
    result = run_scenario(scenario, _scripted_client_factory(responses), budget)
    assert result["passed"], result["reason"]


def test_run_all_stops_at_turn_budget(monkeypatch):
    from firebuddy import config

    monkeypatch.setattr(config, "EVAL_MAX_TURNS", 1)
    scenario = next(s for s in SCENARIOS if s["id"] == "no_fires_monitor")
    two_scenarios = [scenario, scenario]
    # Only one response list: the second scenario's turn should never reach the factory
    # because TurnBudget(1) is exhausted by the first scenario's single turn.
    responses = _tool_then_text("assess_situation", {"place_id": 1}, "MONITOR. Call 911 if unsafe.")
    factory = _scripted_client_factory(responses)
    results = run_all(two_scenarios, factory)
    assert len(results) == 2
    assert results[0]["passed"]
    assert not results[1]["passed"]
    assert "budget" in results[1]["reason"]


def test_turn_budget_raises_when_exceeded():
    budget = TurnBudget(0)
    with pytest.raises(TurnBudgetExceeded):
        budget.take(1)
