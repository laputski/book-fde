from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class GetCarrierStatus(BaseModel):
    """Статус рейса у перевозчика. Вызывать, когда телематика показывает задержку,
    а причина не видна. Не для таможенных задержек."""

    shipment_id: str = Field(pattern=r"^SHP-\d{4}$", description="Идентификатор отправления")
    carrier: str = Field(description="Код перевозчика из телематики")


class NotifyCustomer(BaseModel):
    """Сообщить клиенту о задержке и новом сроке. На одно отправление приходится одно сообщение."""

    shipment_id: str = Field(pattern=r"^SHP-\d{4}$")
    eta_iso: str = Field(description="Новый срок в формате ISO-8601")
    idempotency_key: str = Field(min_length=8, description="Сессия, шаг и аргументы")


@dataclass(frozen=True)
class Tool:
    name: str
    args: type[BaseModel]
    handler: Callable[[BaseModel], str]
    side_effect: bool = False
    timeout_s: float = 3.0

    def descriptor(self) -> dict[str, Any]:
        """То, что увидит модель: имя, назначение, схема аргументов, признак записи."""
        doc = " ".join((self.args.__doc__ or "").split())
        return {"name": self.name, "description": doc,
                "input_schema": self.args.model_json_schema(),
                "side_effect": self.side_effect}


class ToolError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


class Registry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def descriptors(self, *, allow_side_effects: bool = True) -> list[dict[str, Any]]:
        return [t.descriptor() for t in self.tools.values()
                if allow_side_effects or not t.side_effect]

    def call(self, name: str, arguments: Mapping[str, Any]) -> str:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError("unknown_tool", name)
        try:
            args = tool.args.model_validate(dict(arguments))
        except ValidationError as err:
            raise ToolError("invalid_arguments", err.json()) from err
        return tool.handler(args)


if __name__ == "__main__":
    registry = Registry()
    registry.register(Tool("get_carrier_status", GetCarrierStatus,
                           lambda a: "рейс переставлен на 04.03"))
    registry.register(Tool("notify_customer", NotifyCustomer,
                           lambda a: "сообщение отправлено", side_effect=True, timeout_s=10.0))

    schema = registry.descriptors()[0]["input_schema"]
    assert schema["properties"]["shipment_id"]["pattern"] == r"^SHP-\d{4}$"
    assert schema["required"] == ["shipment_id", "carrier"]
    assert "Не для таможенных задержек" in registry.descriptors()[0]["description"]
    assert [d["name"] for d in registry.descriptors(allow_side_effects=False)] == \
           ["get_carrier_status"]

    ok = registry.call("get_carrier_status", {"shipment_id": "SHP-8842", "carrier": "PL-TRUCK"})
    assert ok.startswith("рейс")
    try:
        registry.call("get_carrier_status", {"shipment_id": "8842", "carrier": "PL-TRUCK"})
        raise AssertionError("схема обязана отвергнуть идентификатор без префикса")
    except ToolError as err:
        assert err.code == "invalid_arguments"
    print("схема порождена из типов, запись помечена, аргументы проверены до вызова")
