import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class BlockRecord:
    name: str
    zone: str                     # "prefix" или "suffix"
    tokens: int
    included: bool
    reason: str = ""              # почему блок не вошёл


@dataclass(frozen=True)
class ContextRecord:
    """Что модель увидела в одном запросе и чего не увидела."""

    request_id: str
    prompt_version: str
    blocks: tuple[BlockRecord, ...]

    def names(self, zone: str) -> list[str]:
        return [b.name for b in self.blocks if b.zone == zone and b.included]

    @property
    def prefix_digest(self) -> str:
        seed = self.prompt_version + "|" + "|".join(
            f"{b.name}:{b.tokens}" for b in self.blocks if b.zone == "prefix" and b.included)
        return hashlib.blake2b(seed.encode("utf-8"), digest_size=8).hexdigest()

    @property
    def tokens(self) -> int:
        return sum(b.tokens for b in self.blocks if b.included)

    def dropped(self) -> list[tuple[str, str]]:
        return [(b.name, b.reason) for b in self.blocks if not b.included]


def diff(before: ContextRecord, after: ContextRecord) -> list[str]:
    """Чем второй запрос отличается от первого и почему кэш не сработал."""
    lines: list[str] = []
    if before.prompt_version != after.prompt_version:
        lines.append(f"версия инструкции: {before.prompt_version} → {after.prompt_version}")
    for zone in ("prefix", "suffix"):
        was, now = before.names(zone), after.names(zone)
        added = [n for n in now if n not in was]
        removed = [n for n in was if n not in now]
        if added:
            lines.append(f"{zone}: добавлено {added}")
        if removed:
            lines.append(f"{zone}: убрано {removed}")
        if not added and not removed and was != now:
            lines.append(f"{zone}: порядок изменён {was} → {now}")
    if before.prefix_digest != after.prefix_digest:
        lines.append("кэш промптов: промах, префикс изменился")
    return lines


def record(request_id: str, version: str, prefix: list[tuple[str, int]],
           suffix: list[tuple[str, int]], dropped: list[tuple[str, int, str]]) -> ContextRecord:
    blocks = [BlockRecord(n, "prefix", t, True) for n, t in prefix]
    blocks += [BlockRecord(n, "suffix", t, True) for n, t in suffix]
    blocks += [BlockRecord(n, "suffix", t, False, why) for n, t, why in dropped]
    return ContextRecord(request_id, version, tuple(blocks))


if __name__ == "__main__":
    turn_1 = record("req-1", "2026-03-04",
                    prefix=[("instructions", 1_180), ("tools", 2_400), ("policy", 620)],
                    suffix=[("profile", 300), ("invoices", 740), ("kb:0", 5_900),
                            ("memory", 260), ("history", 1_850), ("question", 40)],
                    dropped=[("kb:1", 6_100, "бюджет: 6100 при остатке 640")])
    turn_2 = record("req-2", "2026-03-04",
                    prefix=[("instructions", 1_180), ("tools", 2_620), ("policy", 620)],
                    suffix=[("profile", 300), ("invoices", 740), ("kb:0", 5_900),
                            ("memory", 300), ("history", 2_100), ("question", 44)],
                    dropped=[("kb:1", 6_100, "бюджет: 6100 при остатке 380")])

    assert turn_1.tokens == 13_290 and turn_1.dropped() == [
        ("kb:1", "бюджет: 6100 при остатке 640")]
    assert turn_1.prefix_digest != turn_2.prefix_digest       # список инструментов вырос

    report = diff(turn_1, turn_2)
    assert report == ["кэш промптов: промах, префикс изменился"]

    turn_3 = record("req-3", "2026-03-11",
                    prefix=[("instructions", 1_240), ("tools", 2_620), ("policy", 620)],
                    suffix=[("profile", 300), ("question", 44)],
                    dropped=[("kb:0", 5_900, "по правилу арендатора: статья другой единицы")])
    lines = diff(turn_2, turn_3)
    assert lines[0].startswith("версия инструкции")
    assert any("убрано" in line and "kb:0" in line for line in lines)
    assert turn_3.dropped()[0][1].startswith("по правилу арендатора")
    print(f"запрос {turn_1.request_id}: {turn_1.tokens} токенов; расхождение: {report}")
