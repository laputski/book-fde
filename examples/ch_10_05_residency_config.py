from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

JURISDICTION = {"eu-north": "eu", "eu-west": "eu", "us-east": "us", "global": "multi"}


class DataClass(IntEnum):
    PUBLIC = 0          # опубликованные правила пособий
    PERSONAL = 1        # заявления и дела жителей
    SPECIAL = 2         # особые категории: здоровье, инвалидность


class Placement(IntEnum):
    REGIONAL_ENDPOINT = 0
    PERIMETER = 1
    SOVEREIGN_CLOUD = 2
    CUSTOMER_GPUS = 3


class Keys(StrEnum):
    PROVIDER = "provider_managed"
    CUSTOMER = "customer_managed"       # ключ в KMS заказчика: отзыв делает данные нечитаемыми
    EXTERNAL = "external_manager"       # ключ вне облака поставщика


class Endpoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    region: str
    self_hosted: bool = False
    retains_prompts: bool = False       # журналы или кэш запросов на стороне поставщика


def required_placement(data: DataClass, exclusive_control: bool, offline: bool) -> Placement:
    """Дерево решений из диаграммы: класс данных, контроль, связь с поставщиком."""
    if data is DataClass.PUBLIC:
        return Placement.REGIONAL_ENDPOINT
    if not exclusive_control:
        return Placement.PERIMETER
    return Placement.CUSTOMER_GPUS if offline else Placement.SOVEREIGN_CLOUD


class Deployment(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    data: DataClass
    jurisdiction: str
    exclusive_control: bool             # ключи и эксплуатация только у заказчика
    offline: bool
    placement: Placement
    storage_region: str
    keys: Keys
    perimeter: bool
    endpoint: Endpoint

    def problems(self) -> list[str]:
        out: list[str] = []
        need = required_placement(self.data, self.exclusive_control, self.offline)
        if self.placement < need:
            out.append(f"размещение {self.placement.name} слабее требуемого {need.name}")
        for what, region in (("хранилище", self.storage_region), ("эндпоинт", self.endpoint.region)):
            if JURISDICTION.get(region) != self.jurisdiction:
                out.append(f"{what} в регионе {region} вне юрисдикции {self.jurisdiction}")
        if self.data >= DataClass.PERSONAL:
            if self.keys is Keys.PROVIDER:
                out.append("персональные данные требуют ключей заказчика")
            if not self.perimeter:
                out.append("персональные данные требуют сервисного периметра")
            if self.endpoint.retains_prompts:
                out.append("эндпоинт хранит запросы: нужен режим без хранения")
        if self.placement >= Placement.SOVEREIGN_CLOUD and self.keys is not Keys.EXTERNAL:
            out.append("суверенное размещение требует ключей вне облака поставщика")
        if self.placement is Placement.CUSTOMER_GPUS and not self.endpoint.self_hosted:
            out.append("без связи с поставщиком модель исполняется на площадке")
        return out

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if problems := self.problems():
            raise ValueError("; ".join(problems))
        return self


def variant(base: Deployment, **changes: object) -> Deployment:
    """model_copy не проверяет модель; вариант собирается заново через валидацию."""
    return Deployment.model_validate(base.model_dump() | changes)


if __name__ == "__main__":
    cases = Deployment(name="citizen-cases", data=DataClass.PERSONAL, jurisdiction="eu",
                       exclusive_control=False, offline=False, placement=Placement.PERIMETER,
                       storage_region="eu-north", keys=Keys.CUSTOMER, perimeter=True,
                       endpoint=Endpoint(region="eu-west"))
    rules = variant(cases, name="benefit-rules", data=DataClass.PUBLIC,
                    placement=Placement.REGIONAL_ENDPOINT, keys=Keys.PROVIDER, perimeter=False)
    assert cases.problems() == [] and rules.problems() == []
    try:
        variant(cases, keys=Keys.PROVIDER, endpoint=Endpoint(region="global", retains_prompts=True))
    except ValidationError as err:
        text = str(err)
        assert "global" in text and "ключей заказчика" in text and "без хранения" in text
    else:
        raise AssertionError("глобальный эндпоинт для дел жителей обязан быть отвергнут")
    try:
        variant(cases, data=DataClass.SPECIAL, exclusive_control=True)
    except ValidationError as err:
        assert "SOVEREIGN_CLOUD" in str(err) and "вне облака" not in str(err)
    else:
        raise AssertionError("особые категории под исключительным контролем требуют суверенного облака")
    print("две конфигурации приняты, две отвергнуты с причинами")
