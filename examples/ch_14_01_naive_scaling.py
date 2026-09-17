from dataclasses import dataclass, field

TPM_QUOTA = 100_000                   # квота проекта: токенов в минуту на модель


class QuotaExceeded(Exception):
    """Ответ 429: квота токенов в минуту исчерпана."""


@dataclass
class FakeModel:
    """Модель за квотой в скользящую минуту; часы в миллисекундах."""
    now_ms: int = 0
    window: list[tuple[int, int]] = field(default_factory=list)

    def generate(self, prompt_tokens: int, max_output: int) -> str:
        self.window = [(t, n) for t, n in self.window if self.now_ms - t < 60_000]
        cost = prompt_tokens + max_output
        if sum(n for _, n in self.window) + cost > TPM_QUOTA:
            self.now_ms += 50                  # отказ приходит быстро
            raise QuotaExceeded("429 RESOURCE_EXHAUSTED")
        self.window.append((self.now_ms, cost))
        self.now_ms += 500                     # ответ модели
        return '{"defect": "scratch", "severity": 2}'


def process_backlog(docs: list[int], model: FakeModel) -> tuple[int, int]:
    done = failed = 0
    for tokens in docs:                        # один документ, один вызов, без пауз
        try:
            model.generate(tokens, max_output=100)
            done += 1
        except QuotaExceeded:
            failed += 1                        # документ потерян, следующий идёт сразу
    return done, failed


if __name__ == "__main__":
    backlog = [1_100] * 1_000                  # утренняя выгрузка нарядов одного завода
    done, failed = process_backlog(backlog, FakeModel())
    assert (done, failed) == (249, 751)         # три четверти выгрузки потеряны
    print(f"обработано {done}, потеряно на квоте {failed}")
