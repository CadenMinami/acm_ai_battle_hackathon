#!/usr/bin/env python3
"""Reference agent: deploys a random card from hand at a random position
within a generous bounding box on the agent's own side of the arena, once
elixir clears a low floor. It relies on the orchestrator/engine's own
legality check (deploy_card) to silently reject anything it can't
actually afford or place yet, rather than tracking exact card costs or
occupied tiles itself.

Deliberately self-contained: it does not import the `clasher` engine
package, since real student agents will eventually run isolated in a
container with no access to orchestrator internals — only the JSON
state arriving over stdin.
"""
import json
import random
import sys

OWN_HALF_Y_RANGES = {
    0: (2.0, 13.0),   # bottom/blue player's side, clear of the river and king tower
    1: (18.0, 29.0),  # top/red player's side
}


def choose_action(state: dict, player_id: int) -> dict:
    hand = state.get("hand", [])
    elixir = state.get("elixir", 0.0)

    if not hand or elixir < 1.0:
        return {"request_id": state["request_id"], "action": "none"}

    card = random.choice(hand)
    y_min, y_max = OWN_HALF_Y_RANGES[player_id]
    x = round(random.uniform(1.0, 17.0), 1)
    y = round(random.uniform(y_min, y_max), 1)

    return {
        "request_id": state["request_id"],
        "action": "deploy",
        "card": card,
        "x": x,
        "y": y,
    }


def main() -> None:
    player_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        state = json.loads(line)
        action = choose_action(state, player_id)
        print(json.dumps(action), flush=True)


if __name__ == "__main__":
    main()
