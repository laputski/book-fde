import hashlib
import re
from dataclasses import dataclass, field

REQUIRED_SECTIONS = ("РОЛЬ", "ГРАНИЦЫ", "ФОРМАТ ОТВЕТА", "ЭСКАЛАЦИЯ")
PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")
MAX_PREFIX_TOKENS = 4_000


class PromptInvalid(Exception):
    """Текст инструкции не проходит проверку и не попадает в реестр."""


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str                  # выпуск, а не «последняя»
    body: str

    @property
    def digest(self) -> str:
        return hashlib.blake2b(self.body.encode("utf-8"), digest_size=8).hexdigest()

    def sections(self) -> list[str]:
        return [line[3:].strip() for line in self.body.splitlines() if line.startswith("## ")]


def check(prompt: Prompt) -> list[str]:
    """Проверки, которые запускает CI на каждом изменении инструкции."""
    problems = []
    missing = [s for s in REQUIRED_SECTIONS if s not in prompt.sections()]
    if missing:
        problems.append(f"нет обязательных разделов: {missing}")
    if PLACEHOLDER.search(prompt.body):
        problems.append("остались неподставленные скобки шаблона")
    if len(prompt.body) // 2 > MAX_PREFIX_TOKENS:
        problems.append("инструкция длиннее бюджета префикса")
    return problems


@dataclass
class PromptRegistry:
    """Выпущенные инструкции: версия неизменна, содержимое адресуется хешем."""

    released: dict[tuple[str, str], Prompt] = field(default_factory=dict)

    def release(self, prompt: Prompt) -> Prompt:
        problems = check(prompt)
        if problems:
            raise PromptInvalid("; ".join(problems))
        key = (prompt.name, prompt.version)
        earlier = self.released.get(key)
        if earlier is not None and earlier.digest != prompt.digest:
            raise PromptInvalid(f"версия {prompt.version} уже выпущена с другим текстом")
        self.released[key] = prompt
        return prompt

    def get(self, name: str, version: str) -> Prompt:
        return self.released[(name, version)]


BODY_V1 = """## РОЛЬ
Ассистент оператора чата Orion Telecom.
## ГРАНИЦЫ
Не обещать компенсацию: это решение оператора.
## ФОРМАТ ОТВЕТА
Вывод, затем ссылка на счёт или статью базы знаний.
## ЭСКАЛАЦИЯ
При аварии в сети передать обращение дежурному инженеру.
"""

if __name__ == "__main__":
    registry = PromptRegistry()
    v1 = registry.release(Prompt("agent_assist", "2026-03-04", BODY_V1))
    assert registry.get("agent_assist", "2026-03-04").digest == v1.digest
    assert v1.digest == Prompt("agent_assist", "2026-03-04", BODY_V1).digest

    without_escalation = BODY_V1.split("## ЭСКАЛАЦИЯ")[0]
    try:
        registry.release(Prompt("agent_assist", "2026-03-05", without_escalation))
        raise AssertionError("инструкция без раздела эскалации не выпускается")
    except PromptInvalid as err:
        assert "ЭСКАЛАЦИЯ" in str(err)

    try:
        registry.release(Prompt("agent_assist", "2026-03-04", BODY_V1 + "Ещё правило.\n"))
        raise AssertionError("выпущенная версия неизменна")
    except PromptInvalid:
        pass

    v2 = registry.release(Prompt("agent_assist", "2026-03-11", BODY_V1 + "## ЯЗЫК\nОтвечать на языке клиента.\n"))
    assert v2.digest != v1.digest                     # другой префикс, другой кэш
    assert check(Prompt("agent_assist", "x", BODY_V1 + "{{tenant}}")) != []
    print(f"выпущено {len(registry.released)} версий, текущая {v2.version} · {v2.digest}")
