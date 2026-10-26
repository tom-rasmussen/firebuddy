import argparse
import json

from firebuddy import db


def print_trace(row) -> None:
    print(f"--- trace #{row['id']} ({row['ts']}) user={row['user_id']} ---")
    print(f"input: {row['input']}")
    for call in json.loads(row["tool_calls"]):
        print(f"  tool {call['name']}({call['input']}) -> {call['result']}")
    print(f"final: {row['final_text']}")
    print(
        f"validator: {row['validator_result']} | retries: {row['retries']} | "
        f"latency: {row['latency_ms']:.0f}ms | tokens in/out: {row['input_tokens']}/{row['output_tokens']}"
    )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Print recent FireBuddy agent traces.")
    parser.add_argument("--last", type=int, default=20)
    args = parser.parse_args()
    with db.session() as conn:
        for row in db.last_traces(conn, args.last):
            print_trace(row)


if __name__ == "__main__":
    main()
