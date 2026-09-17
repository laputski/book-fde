from __future__ import annotations

from dataclasses import dataclass, field


class OntologyError(ValueError):
    """The ontology is not ready for tools to be derived from it."""


@dataclass(frozen=True)
class System:
    id: str
    name: str
    access: str                       # protocol, identity, quotas


@dataclass(frozen=True)
class Entity:
    name: str
    key: str                          # what glues the entity across systems
    systems: tuple[str, ...]          # candidates named during discovery
    freshness: str                    # delay from the event to the read
    copies: tuple[str, ...] = ()      # where it also lives but must not be read from


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
                found.append(f"entity {e.name} is described twice")
            seen.add(e.name)
            if len(e.systems) != 1:
                found.append(f"entity {e.name}: {len(e.systems)} systems of record, exactly one required")
            found.extend(f"entity {e.name}: system {sid} is not described"
                         for sid in e.systems + e.copies if sid not in self.systems)
            if set(e.systems) & set(e.copies):
                found.append(f"entity {e.name}: one system is named both source and copy")
        return found

    def integrations(self) -> list[Integration]:
        """Every arrow from a system of record to an entity is an integration."""
        found = self.problems()
        if found:
            raise OntologyError("; ".join(found))
        return [Integration(e.name, self.systems[e.systems[0]].name,
                            self.systems[e.systems[0]].access, e.freshness)
                for e in self.entities]


def nordbank() -> Ontology:
    systems = [
        System("core", "core banking", "mainframe, SOAP, 40 requests per second"),
        System("crm", "CRM", "REST, OAuth, per-user quota"),
        System("kb", "knowledge base", "REST, ACLs by group"),
        System("tel", "telephony", "transcripts in batches"),
    ]
    entities = [
        Entity("Customer", "customer_id", ("core",), "seconds", copies=("crm",)),
        Entity("Account", "iban", ("core",), "seconds"),
        Entity("Case", "case_id", ("crm",), "seconds"),
        Entity("Agent", "agent_id", ("crm",), "a day"),
        Entity("PolicyDocument", "doc_id", ("kb",), "weeks"),
        Entity("Interaction", "call_id", ("tel",), "15 minutes"),
    ]
    return Ontology(systems={s.id: s for s in systems}, entities=entities)


if __name__ == "__main__":
    onto = nordbank()
    arrows = onto.integrations()
    assert len(arrows) == len(onto.entities) == 6          # six integrations from four systems
    assert {a.system for a in arrows} == {"core banking", "CRM", "knowledge base", "telephony"}
    assert next(a.freshness for a in arrows if a.entity == "Interaction") == "15 minutes"

    onto.entities[0] = Entity("Customer", "customer_id", ("core", "crm"), "seconds")
    try:
        onto.integrations()
        raise AssertionError("two systems of record for one entity must be an error")
    except OntologyError as err:
        assert "2 systems of record" in str(err)
    print(len(arrows), "integrations from", len(onto.systems), "systems of record")
