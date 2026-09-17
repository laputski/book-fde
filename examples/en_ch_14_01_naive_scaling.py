from dataclasses import dataclass, field

TPM_QUOTA = 100_000                   # project quota: tokens per minute per model


class QuotaExceeded(Exception):
    """A 429 answer: the tokens-per-minute quota is exhausted."""


@dataclass
class FakeModel:
    """A model behind a sliding-minute quota; the clock is in milliseconds."""
    now_ms: int = 0
    window: list[tuple[int, int]] = field(default_factory=list)

    def generate(self, prompt_tokens: int, max_output: int) -> str:
        self.window = [(t, n) for t, n in self.window if self.now_ms - t < 60_000]
        cost = prompt_tokens + max_output
        if sum(n for _, n in self.window) + cost > TPM_QUOTA:
            self.now_ms += 50                  # a refusal comes back fast
            raise QuotaExceeded("429 RESOURCE_EXHAUSTED")
        self.window.append((self.now_ms, cost))
        self.now_ms += 500                     # the model's answer
        return '{"defect": "scratch", "severity": 2}'


def process_backlog(docs: list[int], model: FakeModel) -> tuple[int, int]:
    done = failed = 0
    for tokens in docs:                        # one document, one call, no pauses
        try:
            model.generate(tokens, max_output=100)
            done += 1
        except QuotaExceeded:
            failed += 1                        # the document is lost, the next goes at once
    return done, failed


if __name__ == "__main__":
    backlog = [1_100] * 1_000                  # one plant's morning export of work orders
    done, failed = process_backlog(backlog, FakeModel())
    assert (done, failed) == (249, 751)         # three quarters of the export are lost
    print(f"processed {done}, lost to the quota {failed}")
