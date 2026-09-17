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
    code: str = ""              # a machine-readable error code for the model


class ProtocolError(Exception):
    """A JSON-RPC error: the request itself is wrong, and no tool result is produced."""

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
    """The skeleton of an MCP server: a tool list and a checked call."""

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
            raise ProtocolError(-32602, f"Unknown tool: {name}")
        if tool.allowed_groups and not (tool.allowed_groups & principal.groups):
            self.audit.append({"tool": name, "user": principal.user_id, "denied": True})
            return ToolResult("insufficient rights", True, "forbidden")
        try:
            args = tool.args.model_validate(arguments)
        except ValidationError as err:
            return ToolResult(err.json(), True, "invalid_arguments")
        try:
            raw = tool.handler(args, principal)
        except TimeoutError:
            return ToolResult("the system did not answer in time", True, "upstream_timeout")
        self.audit.append({"tool": name, "user": principal.user_id, "args": arguments})
        text = json.dumps(raw, ensure_ascii=False, default=str)
        if len(text.encode("utf-8")) > MAX_RESULT_BYTES:
            return ToolResult("result too large: narrow the query", True, "result_too_large")
        return ToolResult(text)


class SearchAccounts(BaseModel):
    query: str = Field(min_length=3, description="Surname or a fragment of the IBAN")
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
        description=("Find a customer's accounts by surname or a fragment of the IBAN. Use it when "
                     "the operator names the customer but not the account number. Not for transaction history."),
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
        raise AssertionError("an unknown tool must be a protocol error")
    outsider = Principal("op-99", frozenset({"cards"}))
    assert server.call("search_accounts", {"query": "client 1"}, outsider).code == "forbidden"
    assert server.list_tools()[0]["inputSchema"]["properties"]["query"]["minLength"] == 3
    print("the tool is described, bounded and checked")
