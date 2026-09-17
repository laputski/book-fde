import hashlib
import re
from dataclasses import dataclass, field

REQUIRED_SECTIONS = ("ROLE", "BOUNDARIES", "ANSWER FORMAT", "ESCALATION")
PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")
MAX_PREFIX_TOKENS = 4_000


class PromptInvalid(Exception):
    """The text of the instruction fails a check and never enters the registry."""


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str                  # a release, not "the latest"
    body: str

    @property
    def digest(self) -> str:
        return hashlib.blake2b(self.body.encode("utf-8"), digest_size=8).hexdigest()

    def sections(self) -> list[str]:
        return [line[3:].strip() for line in self.body.splitlines() if line.startswith("## ")]


def check(prompt: Prompt) -> list[str]:
    """The checks CI runs on every change to an instruction."""
    problems = []
    missing = [s for s in REQUIRED_SECTIONS if s not in prompt.sections()]
    if missing:
        problems.append(f"required sections are absent: {missing}")
    if PLACEHOLDER.search(prompt.body):
        problems.append("unresolved template braces remain")
    if len(prompt.body) // 2 > MAX_PREFIX_TOKENS:
        problems.append("the instruction is longer than the prefix budget")
    return problems


@dataclass
class PromptRegistry:
    """Released instructions: a version is immutable, the text is addressed by hash."""

    released: dict[tuple[str, str], Prompt] = field(default_factory=dict)

    def release(self, prompt: Prompt) -> Prompt:
        problems = check(prompt)
        if problems:
            raise PromptInvalid("; ".join(problems))
        key = (prompt.name, prompt.version)
        earlier = self.released.get(key)
        if earlier is not None and earlier.digest != prompt.digest:
            raise PromptInvalid(f"version {prompt.version} was released with another text")
        self.released[key] = prompt
        return prompt

    def get(self, name: str, version: str) -> Prompt:
        return self.released[(name, version)]


BODY_V1 = """## ROLE
The assistant of an Orion Telecom chat operator.
## BOUNDARIES
Never promise compensation: that decision belongs to the operator.
## ANSWER FORMAT
The conclusion, then a link to the invoice or the knowledge base article.
## ESCALATION
On a network outage, hand the chat to the engineer on duty.
"""

if __name__ == "__main__":
    registry = PromptRegistry()
    v1 = registry.release(Prompt("agent_assist", "2026-03-04", BODY_V1))
    assert registry.get("agent_assist", "2026-03-04").digest == v1.digest
    assert v1.digest == Prompt("agent_assist", "2026-03-04", BODY_V1).digest

    without_escalation = BODY_V1.split("## ESCALATION")[0]
    try:
        registry.release(Prompt("agent_assist", "2026-03-05", without_escalation))
        raise AssertionError("an instruction without an escalation section is not released")
    except PromptInvalid as err:
        assert "ESCALATION" in str(err)

    try:
        registry.release(Prompt("agent_assist", "2026-03-04", BODY_V1 + "One more rule.\n"))
        raise AssertionError("a released version is immutable")
    except PromptInvalid:
        pass

    v2 = registry.release(Prompt("agent_assist", "2026-03-11", BODY_V1 + "## LANGUAGE\nAnswer in the customer's language.\n"))
    assert v2.digest != v1.digest                     # another prefix, another cache
    assert check(Prompt("agent_assist", "x", BODY_V1 + "{{tenant}}")) != []
    print(f"{len(registry.released)} versions released, current {v2.version} · {v2.digest}")
