from __future__ import annotations

from dataclasses import dataclass, field


class OntologyError(ValueError):
    """Онтология не готова к тому, чтобы выводить из неё инструменты."""


@dataclass(frozen=True)
class System:
    id: str
    name: str
    access: str                       # протокол, идентичность, лимиты


@dataclass(frozen=True)
class Entity:
    name: str
    key: str                          # чем сущность склеивается между системами
    systems: tuple[str, ...]          # кандидаты, названные на discovery
    freshness: str                    # задержка от события до чтения
    copies: tuple[str, ...] = ()      # где лежит ещё, но откуда читать нельзя


@dataclass(frozen=True)
class Integration:
    entity: str
    system: str
    access: str
    freshness: str


@dataclass
class Ontology:
    systems: dict[str, System] = field(default_factory=dict)
    entities: list[Entity] = field(default_factory=list)

    def problems(self) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for e in self.entities:
            if e.name in seen:
                found.append(f"«{e.name}»: сущность описана дважды")
            seen.add(e.name)
            if len(e.systems) != 1:
                found.append(f"«{e.name}»: систем записи {len(e.systems)}, требуется ровно одна")
            found.extend(f"«{e.name}»: система {sid} не описана"
                         for sid in e.systems + e.copies if sid not in self.systems)
            if set(e.systems) & set(e.copies):
                found.append(f"«{e.name}»: одна система названа и источником, и копией")
        return found

    def integrations(self) -> list[Integration]:
        """Каждая стрелка от системы записи к сущности является интеграцией."""
        found = self.problems()
        if found:
            raise OntologyError("; ".join(found))
        return [Integration(e.name, self.systems[e.systems[0]].name,
                            self.systems[e.systems[0]].access, e.freshness)
                for e in self.entities]


def nordbank() -> Ontology:
    systems = [
        System("core", "core banking", "mainframe, SOAP, 40 запросов в секунду"),
        System("crm", "CRM", "REST, OAuth, лимит на пользователя"),
        System("kb", "база знаний", "REST, ACL по группам"),
        System("tel", "телефония", "транскрипты пакетами"),
    ]
    entities = [
        Entity("Клиент", "customer_id", ("core",), "секунды", copies=("crm",)),
        Entity("Счёт", "iban", ("core",), "секунды"),
        Entity("Обращение", "case_id", ("crm",), "секунды"),
        Entity("Оператор", "agent_id", ("crm",), "сутки"),
        Entity("Документ политики", "doc_id", ("kb",), "недели"),
        Entity("Взаимодействие", "call_id", ("tel",), "15 минут"),
    ]
    return Ontology(systems={s.id: s for s in systems}, entities=entities)


if __name__ == "__main__":
    onto = nordbank()
    arrows = onto.integrations()
    assert len(arrows) == len(onto.entities) == 6          # шесть интеграций из четырёх систем
    assert {a.system for a in arrows} == {"core banking", "CRM", "база знаний", "телефония"}
    assert next(a.freshness for a in arrows if a.entity == "Взаимодействие") == "15 минут"

    onto.entities[0] = Entity("Клиент", "customer_id", ("core", "crm"), "секунды")
    try:
        onto.integrations()
        raise AssertionError("две системы записи у одной сущности обязаны быть ошибкой")
    except OntologyError as err:
        assert "систем записи 2" in str(err)
    print(len(arrows), "интеграций из", len(onto.systems), "систем записи")
