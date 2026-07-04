#!/usr/bin/env python3
"""Controllable test double for AgentProcess tests. Mode is picked via
argv[1]: 'echo' (well-behaved), 'sleep' (misses every deadline),
'garbage' (sends invalid JSON), 'crash' (exits immediately)."""
import json
import sys
import time


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "echo"

    if mode == "crash":
        sys.exit(1)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)

        if mode == "sleep":
            time.sleep(5.0)
        elif mode == "garbage":
            print("not json", flush=True)
            continue

        response = {"request_id": request["request_id"], "action": "none"}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
