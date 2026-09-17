# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import count_tokens  # noqa: F401
# --- the listing ---
import hashlib
from dataclasses import dataclass, field
from typing import Literal

BUDGET_TOKENS = 32_000
Zone = Literal["prefix", "suffix"]

INSTRUCTIONS = "## РОЛЬ\nАссистент оператора чата Orion Telecom.\n" + "Правило поведения. " * 200
TOOLS = "## ИНСТРУМЕНТЫ\n" + "get_invoice(subscriber_id, period) -> Invoice\n" * 120
POLICY = "## ФОРМАТ ОТВЕТА\nСначала вывод, затем ссылка на счёт или статью базы знаний.\n"


class BudgetExceeded(Exception):
    """Обязательная часть контекста не помещается в окно."""


@dataclass(frozen=True)
class ContextBlock:
    """Кусок контекста с ценой в токенах, приоритетом и зоной кэширования."""

    name: str
    text: str
    priority: int                 # 1 исключается последним
    zone: Zone = "suffix"
    required: bool = False

    @property
    def tokens(self) -> int:
        return count_tokens(self.render())

    def render(self) -> str:
        return f"<{self.name}>\n{self.text}\n</{self.name}>\n"


@dataclass
class Assembly:
    prefix: str
    suffix: str
    included: list[str] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.prefix + self.suffix

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)

    @property
    def prefix_digest(self) -> str:
        return hashlib.blake2b(self.prefix.encode("utf-8"), digest_size=8).hexdigest()


def assemble(blocks: list[ContextBlock], budget: int = BUDGET_TOKENS) -> Assembly:
    """Отбор по приоритету, размещение по объявленному порядку."""
    prefix_blocks = [b for b in blocks if b.zone == "prefix"]
    suffix_blocks = [b for b in blocks if b.zone == "suffix"]
    prefix = "".join(b.render() for b in prefix_blocks)
    spent = count_tokens(prefix)
    if spent > budget:
        raise BudgetExceeded(f"префикс занимает {spent} токенов из {budget}")

    chosen: set[str] = set()
    excluded: list[tuple[str, str]] = []
    for block in sorted(suffix_blocks, key=lambda b: (b.priority, b.name)):
        if spent + block.tokens <= budget:
            chosen.add(block.name)
            spent += block.tokens
        elif block.required:
            raise BudgetExceeded(f"обязательный блок {block.name} не помещается")
        else:
            excluded.append((block.name, f"бюджет: {block.tokens} при остатке {budget - spent}"))

    ordered = [b for b in suffix_blocks if b.name in chosen]
    return Assembly(prefix=prefix, suffix="".join(b.render() for b in ordered),
                    included=[b.name for b in prefix_blocks] + [b.name for b in ordered],
                    excluded=sorted(excluded))


def request_blocks(profile: str, invoices: str, passages: list[str],
                   summary: str, tail: list[str], question: str) -> list[ContextBlock]:
    """Один запрос agent-assist: неизменная зона, затем данные обращения."""
    blocks = [
        ContextBlock("instructions", INSTRUCTIONS, priority=1, zone="prefix", required=True),
        ContextBlock("tools", TOOLS, priority=1, zone="prefix", required=True),
        ContextBlock("policy", POLICY, priority=1, zone="prefix", required=True),
        ContextBlock("profile", profile, priority=2),
        ContextBlock("invoices", invoices, priority=2),
    ]
    blocks += [ContextBlock(f"kb:{i}", text, priority=3 + i) for i, text in enumerate(passages)]
    blocks += [
        ContextBlock("memory", summary, priority=2),
        ContextBlock("history", "\n".join(tail), priority=2),
        ContextBlock("question", question, priority=1, required=True),
    ]
    return blocks


if __name__ == "__main__":
    passages = ["Статья базы знаний о двойном списании. " * 620,
                "Статья о переносе платежа между лицевыми счетами. " * 480,
                "Статья об аварии в сегменте сети и компенсации. " * 500]
    tail = [f"клиент: реплика {i}" for i in range(20)]

    first = assemble(request_blocks("Пётр Ильин, Orion S", "счёт 1204 на 1490 рублей",
                                    passages, "клиент уже жаловался в марте",
                                    tail, "почему списали дважды?"))
    second = assemble(request_blocks("Мария Ким, Orion L", "счёт 8831 на 3200 рублей",
                                     passages, "новых обращений не было",
                                     tail, "как перенести платёж?"))

    assert first.tokens <= BUDGET_TOKENS and second.tokens <= BUDGET_TOKENS
    assert first.prefix == second.prefix                  # префикс совпадает байт в байт
    assert first.prefix_digest == second.prefix_digest
    assert "question" in first.included                   # обязательный блок на месте
    assert [n for n, _ in first.excluded] == ["kb:2"]     # вытеснен блок с худшим приоритетом
    assert first.included.index("memory") < first.included.index("question")

    tight = assemble(request_blocks("Пётр Ильин, Orion S", "счёт 1204 на 1490 рублей",
                                    passages, "клиент уже жаловался в марте",
                                    tail, "почему списали дважды?"), budget=4_000)
    assert tight.included[-1] == "question"               # вопрос уцелел
    assert [n for n, _ in tight.excluded] == ["kb:0", "kb:1", "kb:2"]

    try:
        assemble(request_blocks("Пётр Ильин, Orion S", "счёт 1204 на 1490 рублей",
                                passages, "", tail, "почему?"), budget=1_000)
        raise AssertionError("нехватка бюджета обязана быть отказом, а не усечением")
    except BudgetExceeded:
        pass
    print(f"собрано {first.tokens} токенов, префикс {first.prefix_digest}, "
          f"вытеснено {len(first.excluded)}")
