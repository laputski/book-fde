from __future__ import annotations

import json

TELEMATICS = {"SHP-8842": {"delay_h": 9, "last_scan": "Wrocław", "temp_c": 4}}


def call_tool(name: str, args: dict[str, str]) -> str:
    if name == "get_telematics":
        return json.dumps(TELEMATICS[args["shipment_id"]])
    return "{}"


class ScriptedModel:
    """Заглушка модели: сначала вызовы инструментов, затем текст ответа."""

    def __init__(self) -> None:
        self.turn = 0

    def next(self, history: list[str]) -> tuple[str, dict[str, str]] | str:
        self.turn += 1
        if self.turn <= 3:
            return "get_telematics", {"shipment_id": "SHP-8842"}
        return "задержка 9 часов, груз в Вроцлаве"


def run(question: str) -> tuple[str, list[str]]:
    model = ScriptedModel()
    history = [question]
    while True:                                  # ни шагов, ни времени, ни денег
        step = model.next(history)
        if isinstance(step, str):
            return step, history
        name, args = step
        history.append(call_tool(name, args))


if __name__ == "__main__":
    answer, history = run("что с отправлением SHP-8842?")
    assert answer.startswith("задержка")
    assert len(history) == 4                     # вопрос и три одинаковых вызова
    print("ответ получен за 3 вызова; цикл остановил сценарий, а не бюджет")
