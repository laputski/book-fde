from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


class Layer(StrEnum):
    CHANNELS = "каналы"
    RUNTIME = "среда исполнения агента"
    TOOLS = "инструменты и интеграция"
    DATA = "данные и поиск"
    EVALUATION = "оценка и наблюдаемость"
    GOVERNANCE = "безопасность и управление"


class Hosting(StrEnum):
    MANAGED = "managed"          # сервис поставщика, эксплуатирует поставщик
    TENANT = "in_tenancy"        # облачный проект заказчика, эксплуатирует заказчик
    ON_SITE = "on_site"          # площадка без связи с облаком


class Driver(StrEnum):
    RESIDENCY = "резидентность"
    VOLUME = "стабильность объёма"
    LATENCY = "задержка"
    OPERATIONS = "эксплуатация"
    REGULATION = "регуляторика"


@dataclass(frozen=True)
class Option:
    name: str
    hosting: Hosting
    ops_fte: float = 0.0         # эксплуатация на стороне заказчика, ставок
    residency: bool = True       # обработка и ключи остаются в юрисдикции заказчика
    commitment: bool = False     # мощность оплачивается на срок вперёд


@dataclass(frozen=True)
class Point:
    number: int
    component: str
    layer: Layer
    drivers: frozenset[Driver]
    options: tuple[Option, ...]


M, T, S = Hosting.MANAGED, Hosting.TENANT, Hosting.ON_SITE
D = Driver
FIXED = {Layer.CHANNELS: "единый API агента", Layer.TOOLS: "политика вне модели",
         Layer.DATA: "системы записи", Layer.EVALUATION: "ворота оценки", Layer.GOVERNANCE: "журнал аудита"}
POINTS = {p.number: p for p in (
    Point(1, "агентный цикл", Layer.RUNTIME, frozenset({D.OPERATIONS, D.RESIDENCY}),
          (Option("managed_runtime", M), Option("container", T, 0.5), Option("edge_container", S, 0.5))),
    Point(2, "эндпоинт модели", Layer.RUNTIME, frozenset({D.VOLUME, D.LATENCY, D.RESIDENCY}),
          (Option("paygo_regional", M), Option("paygo_global", M, residency=False),
           Option("provisioned", M, commitment=True), Option("open_weights", T, 1.5),
           Option("open_weights_edge", S, 1.0))),
    Point(3, "MCP-серверы", Layer.TOOLS, frozenset({D.REGULATION}),
          (Option("mcp_in_perimeter", T, 0.5), Option("mcp_on_site", S, 0.5))),
    Point(4, "индекс поиска", Layer.DATA, frozenset({D.RESIDENCY, D.VOLUME}),
          (Option("managed_index", M), Option("pgvector", T, 0.3), Option("local_index", S, 0.3))),
    Point(5, "трассы и оценки", Layer.EVALUATION, frozenset({D.REGULATION, D.OPERATIONS}),
          (Option("managed_traces", M), Option("self_hosted_traces", T, 0.4), Option("outbox_sync", S, 0.2))),
    Point(6, "ключи и периметр", Layer.GOVERNANCE, frozenset({D.RESIDENCY, D.REGULATION}),
          (Option("provider_keys", M, residency=False), Option("customer_keys", M),
           Option("site_keys", S, 0.2))),
)}


def driven_by(driver: Driver) -> list[int]:
    """Какие решения пересматриваются, если меняется драйвер."""
    return sorted(n for n, p in POINTS.items() if driver in p.drivers)


@dataclass(frozen=True)
class Site:
    name: str
    air_gapped: bool
    residency: bool
    ops_fte: float               # сколько эксплуатации заказчик способен держать
    stable_volume: bool


class Blueprint(BaseModel):
    model_config = ConfigDict(frozen=True)
    site: Site
    choices: dict[int, str]

    def problems(self) -> list[str]:
        out: list[str] = []
        ops = 0.0
        for n, point in POINTS.items():
            chosen = self.choices.get(n)
            option = next((o for o in point.options if o.name == chosen), None)
            where = f"точка {n} ({point.component})"
            if option is None:
                out.append(f"{where}: вариант {chosen!r} отсутствует в каталоге")
                continue
            ops += option.ops_fte
            if self.site.air_gapped and option.hosting is not Hosting.ON_SITE:
                out.append(f"{where}: {option.name} требует связи с облаком")
            if self.site.residency and not option.residency:
                out.append(f"{where}: {option.name} не гарантирует резидентность")
            if option.commitment and not self.site.stable_volume:
                out.append(f"{where}: обязательство по мощности без стабильной базы")
        if ops > self.site.ops_fte:
            out.append(f"эксплуатация {ops:.1f} ставки при доступных {self.site.ops_fte:.1f}")
        return out

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if problems := self.problems():
            raise ValueError("; ".join(problems))
        return self


def rebind(base: Blueprint, number: int, option: str) -> Blueprint:
    """model_copy не запускает валидацию, поэтому вариант собирается заново."""
    return Blueprint.model_validate({"site": base.site, "choices": base.choices | {number: option}})


if __name__ == "__main__":
    northgate = Site("Northgate", air_gapped=False, residency=True, ops_fte=1.5, stable_volume=False)
    helix = Site("Helix, завод 12", air_gapped=True, residency=True, ops_fte=3.0, stable_volume=True)
    city = Blueprint(site=northgate, choices={1: "managed_runtime", 2: "paygo_regional", 3: "mcp_in_perimeter",
                                              4: "managed_index", 5: "managed_traces", 6: "customer_keys"})
    plant = Blueprint(site=helix, choices={1: "edge_container", 2: "open_weights_edge", 3: "mcp_on_site",
                                           4: "local_index", 5: "outbox_sync", 6: "site_keys"})
    assert set(FIXED) | {p.layer for p in POINTS.values()} == set(Layer)   # ни один слой не забыт
    assert driven_by(Driver.RESIDENCY) == [1, 2, 4, 6]        # вопрос, на который слайд не отвечает
    rejected = [(plant, 1, "managed_runtime", "точка 1 (агентный цикл): managed_runtime требует связи"),
                (city, 2, "paygo_global", "не гарантирует резидентность"),
                (city, 2, "provisioned", "без стабильной базы"),
                (city, 2, "open_weights", "эксплуатация 2.0 ставки при доступных 1.5")]
    for base, number, option, reason in rejected:
        try:
            rebind(base, number, option)
        except ValidationError as err:
            assert reason in str(err), str(err)
        else:
            raise AssertionError(f"{option} в точке {number} обязан быть отвергнут")
    print("две привязки приняты, четыре отвергнуты с указанием точки")
