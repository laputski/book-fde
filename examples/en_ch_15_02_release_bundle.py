from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_version: str                              # a pinned version, not an alias
    prompt_sha: str                                 # a hash of the prompt content
    index_snapshot: str                             # an immutable snapshot, not an index name
    parser_version: str                             # the PDF parser that built the snapshot
    tool_schemas: tuple[tuple[str, str], ...]       # (tool, schema hash)
    config_sha: str

    def bundle_id(self) -> str:
        return "b-" + sha(self.model_dump_json())

    def diff(self, other: Manifest) -> list[str]:
        mine, theirs = self.model_dump(), other.model_dump()
        return sorted(key for key in mine if mine[key] != theirs[key])


@dataclass
class Registry:
    now: Callable[[], str]
    bundles: dict[str, Manifest] = field(default_factory=dict)
    gate: dict[str, bool] = field(default_factory=dict)             # the evaluation gate verdict
    active: str = ""
    history: list[tuple[str, str, str]] = field(default_factory=list)   # (when, from, to)

    def register(self, manifest: Manifest) -> str:
        self.bundles[manifest.bundle_id()] = manifest
        return manifest.bundle_id()

    def record_gate(self, bundle_id: str, passed: bool) -> None:
        self.gate[bundle_id] = passed

    def activate(self, bundle_id: str) -> None:
        if self.gate.get(bundle_id) is not True:
            raise PermissionError(f"{bundle_id}: this combination never passed the evaluation gate")
        self.history.append((self.now(), self.active, bundle_id))
        self.active = bundle_id                     # one assignment: every component at once

    def rollback(self) -> str:
        previous = self.history[-1][1]
        self.activate(previous)
        return previous

    def active_at(self, moment: str) -> str:
        switched = [to for when, _, to in self.history if when <= moment]
        return switched[-1] if switched else ""


if __name__ == "__main__":
    clock = {"t": "2026-09-12T22:00"}
    reg = Registry(now=lambda: clock["t"])
    old_prompt = "Answer from the guidelines and name the edition of the source."
    new_prompt = "Briefly: dose, frequency, source. Example: 'G-12, edition 7, section 4.2'."
    r118 = Manifest(model_version="model-pro-2026-06-01", prompt_sha=sha(old_prompt),
                    index_snapshot="snap-2026-09-12", parser_version="pdfparse-2.8",
                    tool_schemas=(("search_guidelines", sha("q: str, dept: str")),),
                    config_sha=sha("temperature=0.2"))
    good = reg.register(r118)
    reg.record_gate(good, passed=True)
    reg.activate(good)

    clock["t"] = "2026-09-13T22:00"
    r119 = r118.model_copy(update={"prompt_sha": sha(new_prompt), "index_snapshot": "snap-2026-09-13"})
    bad = reg.register(r119)
    reg.record_gate(bad, passed=True)               # the eval set has no questions on edition 8
    reg.activate(bad)

    assert reg.active_at("2026-09-14T09:10") == bad
    assert reg.bundles[bad].diff(reg.bundles[good]) == ["index_snapshot", "prompt_sha"]

    mixed = reg.register(r119.model_copy(update={"prompt_sha": sha(old_prompt)}))
    try:
        reg.activate(mixed)                         # a partial rollback: the prompt only
        raise AssertionError("an unevaluated combination was activated")
    except PermissionError:
        pass

    clock["t"] = "2026-09-14T10:05"
    assert reg.rollback() == good and reg.active == good
    assert reg.bundles[reg.active].diff(r118) == []         # every component came back together
    assert reg.active_at("2026-09-14T09:10") == bad         # history is not rewritten
    print("the bundle switches and rolls back as a whole; the unevaluated mix is refused")
