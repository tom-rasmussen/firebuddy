"""Eval CLI: run the scenario suite against the real Claude model + fixtures.

Requires ANTHROPIC_API_KEY. Caps the whole run at EVAL_MAX_TURNS agent turns
(section 0's spend guardrail). Usage: python -m evals.run_evals
"""

import sys

from evals.runner import run_all
from evals.scenarios import SCENARIOS
from firebuddy import config

# claude-sonnet-5-5 list pricing per MTok, confirmed live 2026-10-26 against
# platform.claude.com/docs/en/about-claude/models/overview (newer than this
# model's absence from any locally cached pricing table).
INPUT_COST_PER_MTOK = 2.00
OUTPUT_COST_PER_MTOK = 10.00


def main() -> int:
    if not config.ANTHROPIC_API_KEY:
        print("BLOCKED: set ANTHROPIC_API_KEY to run the live eval suite against the real model.")
        print(f"{len(SCENARIOS)} scenarios are defined and ready in evals/scenarios.py.")
        return 1

    from firebuddy.agent import AnthropicLLMClient

    results = run_all(SCENARIOS, lambda: AnthropicLLMClient())

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{len(results)} scenarios passed\n")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['id']}: {r['title']}")
        if not r["passed"]:
            print(f"        reason: {r['reason']}")
    ungrounded = sum(1 for r in results for v in r["validator_results"] if not v.startswith("ok"))
    print(f"\nungrounded/failed-validator turns across all scenarios: {ungrounded}")

    total_input = sum(r.get("input_tokens", 0) for r in results)
    total_output = sum(r.get("output_tokens", 0) for r in results)
    cost = (total_input / 1_000_000) * INPUT_COST_PER_MTOK + (total_output / 1_000_000) * OUTPUT_COST_PER_MTOK
    print(f"tokens: {total_input} in / {total_output} out ({config.ANTHROPIC_MODEL})")
    print(f"estimated cost: ${cost:.4f}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
