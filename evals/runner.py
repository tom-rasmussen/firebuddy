import json

from firebuddy import config, db
from firebuddy.sources import fires as fires_source
from firebuddy.sources import nws as nws_source
from firebuddy.sources import shelters as shelters_source

HOME_ADDRESS = "3301 Camino Tassajara, Danville, CA"
HOME_LAT, HOME_LON = 37.799427724049, -121.924273999184


class TurnBudgetExceeded(Exception):
    pass


class TurnBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.spent = 0

    def take(self, n: int = 1) -> None:
        if self.spent + n > self.limit:
            raise TurnBudgetExceeded(f"eval turn budget exceeded ({self.spent}+{n} > {self.limit})")
        self.spent += n


def _install_world(world: dict):
    originals = (fires_source.fires_near, nws_source.official_alerts, nws_source.wind_data,
                 shelters_source.find_shelters)

    fires_source.fires_near = lambda lat, lon, radius: world["fires"]
    nws_source.official_alerts = lambda lat, lon: world["alerts"]
    nws_source.wind_data = lambda lat, lon: world["wind"]
    shelters_source.find_shelters = lambda lat, lon, max_results=3: world["shelters"][:max_results]
    return originals


def _restore_world(originals):
    fires_source.fires_near, nws_source.official_alerts, nws_source.wind_data, shelters_source.find_shelters = (
        originals
    )


def run_scenario(scenario: dict, llm_client_factory, budget: TurnBudget) -> dict:
    conn = db.connect(":memory:")
    db.init_db(conn)
    phone = f"+1555{abs(hash(scenario['id'])) % 10_000_000:07d}"
    user = db.get_or_create_user(conn, phone)
    place = db.add_place(conn, user["id"], "Home", HOME_ADDRESS, HOME_LAT, HOME_LON, 15)

    originals = _install_world(scenario["world"])
    try:
        tool_calls, final_texts, validator_results = [], [], []
        input_tokens = output_tokens = 0
        for turn_text in scenario["turns"]:
            budget.take(1)
            llm_client = llm_client_factory()
            reply = _run_turn(conn, user, turn_text, llm_client)
            final_texts.append(reply)
            trace = db.last_traces(conn, 1)[0]
            validator_results.append(trace["validator_result"])
            tool_calls.extend(json.loads(trace["tool_calls"]))
            input_tokens += trace["input_tokens"] or 0
            output_tokens += trace["output_tokens"] or 0

        ctx = {
            "tool_calls": tool_calls,
            "final_texts": final_texts,
            "validator_results": validator_results,
            "places_after": db.list_places(conn, user["id"]),
            "followups_after": _all_followups(conn, user["id"]),
            "place": place,
        }
        passed, reason = scenario["check"](ctx)
        return {"id": scenario["id"], "title": scenario["title"], "passed": passed, "reason": reason,
                "final_texts": final_texts, "validator_results": validator_results,
                "input_tokens": input_tokens, "output_tokens": output_tokens}
    finally:
        _restore_world(originals)
        conn.close()


def _all_followups(conn, user_id):
    return conn.execute("SELECT * FROM followups WHERE user_id = ?", (user_id,)).fetchall()


def _run_turn(conn, user, text, llm_client):
    from firebuddy import agent

    return agent.run_turn(conn, user, text, llm_client)


def run_all(scenarios: list[dict], llm_client_factory) -> list[dict]:
    budget = TurnBudget(config.EVAL_MAX_TURNS)
    results = []
    for scenario in scenarios:
        try:
            results.append(run_scenario(scenario, llm_client_factory, budget))
        except TurnBudgetExceeded as exc:
            results.append({"id": scenario["id"], "title": scenario["title"], "passed": False,
                             "reason": str(exc), "final_texts": [], "validator_results": [],
                             "input_tokens": 0, "output_tokens": 0})
            break
    return results
