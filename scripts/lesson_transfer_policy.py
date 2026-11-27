"""Stateless offline decision agent for #126; the simulator is external."""

from operator import eq, ge, lt

OPS = {"eq": eq, "ge": ge, "lt": lt}


def choose(task, memory):
    config = task["configuration"]
    measurements = {
        **config,
        "headroom": config["capacity"] - config["occupied"],
        "deadline_slack": config["deadline"] - config["items"],
    }
    # Both memory types supply scoped, source-linked recommendations to the same matcher.
    for recommendation in memory["recommendations"]:
        if all(
            OPS[op](measurements[field], value) for field, op, value in recommendation["conditions"]
        ):
            return dict(
                action=recommendation["action"],
                cited_sources=recommendation["sources"],
                matched=True,
            )
    return dict(action="direct", cited_sources=[], matched=False)
