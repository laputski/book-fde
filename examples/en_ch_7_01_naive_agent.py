from __future__ import annotations

import json

TELEMATICS = {"SHP-8842": {"delay_h": 9, "last_scan": "Wrocław", "temp_c": 4}}


def call_tool(name: str, args: dict[str, str]) -> str:
    if name == "get_telematics":
        return json.dumps(TELEMATICS[args["shipment_id"]])
    return "{}"


class ScriptedModel:
    """A model stub: tool calls first, then the text of the answer."""

    def __init__(self) -> None:
        self.turn = 0

    def next(self, history: list[str]) -> tuple[str, dict[str, str]] | str:
        self.turn += 1
        if self.turn <= 3:
            return "get_telematics", {"shipment_id": "SHP-8842"}
        return "delay of 9 hours, the cargo is in Wrocław"


def run(question: str) -> tuple[str, list[str]]:
    model = ScriptedModel()
    history = [question]
    while True:                                  # no limit on steps, time or money
        step = model.next(history)
        if isinstance(step, str):
            return step, history
        name, args = step
        history.append(call_tool(name, args))


if __name__ == "__main__":
    answer, history = run("what is happening with shipment SHP-8842?")
    assert answer.startswith("delay")
    assert len(history) == 4                     # the question and three identical calls
    print("answer obtained after 3 calls; the scenario stopped the loop, not a budget")
