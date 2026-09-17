from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

MAX_RESULT_BYTES = 8_000


@dataclass(frozen=True)
class Principal:
    user_id: str
    groups: frozenset[str]


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    code: str = ""              # машинно-читаемый код ошибки для модели


class ProtocolError(Exception):
    """Ошибка JSON-RPC: неверен сам запрос, и результат инструмента не формируется."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    handler: Callable[[BaseModel, Principal], Any]
    side_effect: bool = False
    allowed_groups: frozenset[str] = field(default_factory=frozenset)

    def descriptor(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.args.model_json_schema()}


class McpServer:
    """Каркас MCP-сервера: список инструментов и вызов с проверками."""

    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}
        self.audit: list[dict[str, Any]] = []

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.descriptor() for t in self.tools.values()]

    def call(self, name: str, arguments: dict[str, Any], principal: Principal) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            raise ProtocolError(-32602, f"Неизвестный инструмент: {name}")
        if tool.allowed_groups and not (tool.allowed_groups & principal.groups):
            self.audit.append({"tool": name, "user": principal.user_id, "denied": True})
            return ToolResult("недостаточно прав", True, "forbidden")
        try:
            args = tool.args.model_validate(arguments)
        except ValidationError as err:
            return ToolResult(err.json(), True, "invalid_arguments")
        try:
            raw = tool.handler(args, principal)
        except TimeoutError:
            return ToolResult("система не ответила вовремя", True, "upstream_timeout")
        self.audit.append({"tool": name, "user": principal.user_id, "args": arguments})
        text = json.dumps(raw, ensure_ascii=False, default=str)
        if len(text.encode("utf-8")) > MAX_RESULT_BYTES:
            return ToolResult("результат слишком велик: сузьте запрос", True, "result_too_large")
        return ToolResult(text)


class SearchAccounts(BaseModel):
    query: str = Field(min_length=3, description="Фамилия или фрагмент IBAN")
    limit: int = Field(default=5, ge=1, le=20)


ACCOUNTS = [{"id": str(i), "name": f"client {i}", "iban": f"NB00{i:04d}", "owner_group": "retail"}
            for i in range(2000)]


def search_accounts(args: BaseModel, principal: Principal) -> list[dict[str, str]]:
    assert isinstance(args, SearchAccounts)
    visible = [a for a in ACCOUNTS if a["owner_group"] in principal.groups]
    return [a for a in visible if args.query in a["name"] or args.query in a["iban"]][: args.limit]


if __name__ == "__main__":
    server = McpServer()
    server.register(Tool(
        name="search_accounts",
        description=("Найти счета клиента по фамилии или фрагменту IBAN. Используйте, когда "
                     "оператор называет клиента, но не номер счёта. Не для истории операций."),
        args=SearchAccounts, handler=search_accounts, allowed_groups=frozenset({"retail"})))
    operator = Principal("op-17", frozenset({"retail"}))
    ok = server.call("search_accounts", {"query": "client 1"}, operator)
    assert not ok.is_error and len(json.loads(ok.content)) == 5
    bad = server.call("search_accounts", {"query": "cl"}, operator)
    assert bad.is_error and bad.code == "invalid_arguments"
    try:
        server.call("delete_account", {}, operator)
    except ProtocolError as err:
        assert err.code == -32602
    else:
        raise AssertionError("неизвестный инструмент должен давать ошибку протокола")
    outsider = Principal("op-99", frozenset({"cards"}))
    assert server.call("search_accounts", {"query": "client 1"}, outsider).code == "forbidden"
    assert server.list_tools()[0]["inputSchema"]["properties"]["query"]["minLength"] == 3
    print("инструмент описан, ограничен и проверен")
