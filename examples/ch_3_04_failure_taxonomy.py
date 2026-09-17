from __future__ import annotations

from dataclasses import dataclass


class ModelCallError(Exception):
    """Отказ вызова модели, различённый по способу восстановления."""


class Transient(ModelCallError):
    """429 и 5xx: обращение не выполнено, состояние не изменилось."""

    def __init__(self, message: str, retry_after_s: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class Truncated(ModelCallError):
    """Модель упёрлась в потолок выходных токенов: ответ оборван."""


class SchemaViolation(ModelCallError):
    """Ответ завершён, но не соответствует схеме."""


class Refusal(ModelCallError):
    """Модель отказалась отвечать: тот же промпт даст тот же результат."""


@dataclass(frozen=True)
class Policy:
    attempts: int
    backoff_s: float
    raise_output_limit: bool = False
    to_human: bool = False


POLICIES: dict[type[ModelCallError], Policy] = {
    Transient: Policy(attempts=3, backoff_s=1.0),
    Truncated: Policy(attempts=1, backoff_s=0.0, raise_output_limit=True),
    SchemaViolation: Policy(attempts=1, backoff_s=0.0),
    Refusal: Policy(attempts=0, backoff_s=0.0, to_human=True),
}


@dataclass(frozen=True)
class RawResponse:
    status: int
    finish_reason: str
    text: str
    retry_after_s: float = 1.0


def classify(resp: RawResponse, validates: bool) -> ModelCallError | None:
    """Порядок проверок важен: усечение распознаётся до разбора JSON."""
    if resp.status == 429:
        return Transient("исчерпана квота токенов в минуту", resp.retry_after_s)
    if resp.status >= 500:
        return Transient(f"сторона модели ответила {resp.status}")
    if resp.finish_reason == "length":
        return Truncated("ответ оборван по потолку выходных токенов")
    if resp.finish_reason == "refusal":
        return Refusal("модель отказалась отвечать по этому документу")
    if not validates:
        return SchemaViolation("ответ завершён, но не соответствует схеме")
    return None


def policy_for(err: ModelCallError) -> Policy:
    for klass in type(err).__mro__:
        if klass in POLICIES:
            return POLICIES[klass]
    raise KeyError(type(err).__name__)


if __name__ == "__main__":
    cut = RawResponse(200, "length", '{"items": [{"hs_code": "8703.')
    truncated = classify(cut, validates=False)
    assert isinstance(truncated, Truncated)          # не SchemaViolation
    assert policy_for(truncated).raise_output_limit

    limited = classify(RawResponse(429, "stop", "", retry_after_s=4.0), validates=True)
    assert isinstance(limited, Transient) and limited.retry_after_s == 4.0
    assert policy_for(limited).attempts == 3

    refused = classify(RawResponse(200, "refusal", ""), validates=True)
    assert isinstance(refused, Refusal)
    assert policy_for(refused).attempts == 0 and policy_for(refused).to_human

    broken = classify(RawResponse(200, "stop", "{"), validates=False)
    assert isinstance(broken, SchemaViolation) and policy_for(broken).attempts == 1
    assert classify(RawResponse(200, "stop", "{}"), validates=True) is None
    print("четыре класса отказов различены, каждому назначена своя политика")
