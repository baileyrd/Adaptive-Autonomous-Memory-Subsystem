"""Fresh, deterministic #125 citation-pressure histories and scoring keys."""

import json
from hashlib import sha256

EXPECTED = {"blocking": "stop", "second_original": "proceed", "conflict": "abstain"}
ATTRIBUTION = ("unlinked", "partial", "linked")
CONTROL_MODES = ("absent", "withheld", "foreign", "recorded_late", "effective_late")


def fixtures():
    cases, labels = [], {}
    for outcome, expected in EXPECTED.items():
        for attribution in ATTRIBUTION:
            for index in range(4):
                key = sha256(
                    f"aams-eight-citation/{outcome}/{attribution}/{index}".encode()
                ).hexdigest()[:14]
                scope, topic = f"pressure-dock-{key}", f"pressure-load-{key}"
                task = dict(
                    id=key, scope=scope, topic=topic, checks=["seal"], day=6, as_of=6, allowed=True
                )
                observations, receipts, links = [], {}, []

                def record(order, *, state="clear", observed=2, slot=None):
                    rid = f"{key}-{order:02}"
                    payload = json.dumps(
                        dict(topic=topic, check="seal", state=state), sort_keys=True
                    )
                    observations.append(
                        dict(
                            id=rid,
                            scope=scope,
                            source=rid,
                            observed=observed,
                            recorded=observed,
                            text=payload,
                        )
                    )
                    if slot is not None:
                        receipts[rid] = f"inspection-{slot}"
                    return rid

                clear_time = 3 if outcome == "conflict" else 2
                first = record(0, observed=clear_time, slot=1)
                if outcome != "second_original":
                    record(1, observed=clear_time, slot=2)
                count = 8 - len(observations) + int(attribution == "partial")
                for i in range(count):
                    child = record(10 + i, observed=clear_time)
                    if attribution == "linked" or (
                        attribution == "partial" and i == index % (count - 1)
                    ):
                        links.append(
                            dict(
                                child=child,
                                parent=first,
                                scope=scope,
                                principal="pilot",
                                granted=True,
                                recorded=4,
                                effective=3,
                            )
                        )
                if outcome == "second_original":
                    decisive = record(99, slot=2)
                else:
                    decisive = record(99, state="blocked", observed=3, slot=3)

                cases.append(
                    dict(
                        id=key,
                        family=f"{outcome}/{attribution}",
                        attribution=attribution,
                        task=task,
                        observations=observations,
                        receipts=receipts,
                        links=links,
                        extra=child,
                        decisive=decisive,
                    )
                )
                labels[key] = dict(expected=expected)
    return cases, labels
