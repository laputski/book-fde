from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Crm:
    """Внешняя система: сохраняет данные после перезапуска исполнителя."""
    letters: list[str] = field(default_factory=list)


@dataclass
class Worker:
    crm: Crm
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)   # хранится в памяти процесса

    def advance(self, customer: str) -> str:
        run = self.runs.setdefault(customer, {"step": "assess"})
        if run["step"] == "assess":
            run["missing"] = ["proof_of_address"]
            run["step"] = "request"
        elif run["step"] == "request":
            self.crm.letters.append(customer)          # запрос документов клиенту
            run["step"] = "wait_for_customer"
        return str(run["step"])


if __name__ == "__main__":
    crm = Crm()
    worker = Worker(crm)
    worker.advance("C-104233")
    assert worker.advance("C-104233") == "wait_for_customer" and len(crm.letters) == 1

    worker = Worker(crm)                               # выкладка: новый процесс
    assert worker.runs == {}                           # досье в работе забыты
    worker.advance("C-104233")
    worker.advance("C-104233")
    assert len(crm.letters) == 2                       # клиент получил второй запрос
    print("перезапуск стёр состояние, и клиент получил запрос дважды")
