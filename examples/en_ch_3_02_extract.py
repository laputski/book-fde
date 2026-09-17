from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

PRICE_PER_MTOK = {"flash": (0.15, 0.60), "pro": (1.25, 5.00)}   # input, output
CACHE_DISCOUNT = 0.25          # share of the input price for a token read from cache
MAX_INPUT_TOKENS = 12_000
MAX_OUTPUT_TOKENS = 900


def count_tokens(text: str) -> int:
    """A stable approximation: four characters per token, Cyrillic twice as dear."""
    cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    return max(1, (len(text) - cyrillic) // 4 + cyrillic // 2)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


@dataclass(frozen=True)
class Reply:
    text: str
    finish_reason: str         # "stop" | "length" | "refusal"
    usage: Usage


class ModelClient(Protocol):
    def generate(self, prompt: str, *, schema: dict[str, Any],
                 max_output_tokens: int) -> Reply: ...


class FakeModel:
    """Answers from a script: the first answer breaks the schema, the second obeys it."""

    def __init__(self, replies: list[str], cached: int = 0) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.cached = cached

    def generate(self, prompt: str, *, schema: dict[str, Any],
                 max_output_tokens: int) -> Reply:
        self.prompts.append(prompt)
        text = self.replies.pop(0)
        produced = count_tokens(text)
        finish = "length" if produced > max_output_tokens else "stop"
        return Reply(text, finish, Usage(count_tokens(prompt),
                                         min(produced, max_output_tokens), self.cached))


class LineItem(BaseModel):
    hs_code: str = Field(pattern=r"^\d{4}\.\d{2}$")
    description: str = Field(min_length=2, max_length=120)
    quantity: int = Field(ge=1)
    value_eur: float = Field(ge=0)


class Declaration(BaseModel):
    """The contract between the model and SAP: what counts as an extracted document."""

    shipment_id: str = Field(pattern=r"^TKL-\d{6}$")
    origin: str = Field(pattern=r"^[A-Z]{2}$")
    incoterm: str = Field(pattern=r"^[A-Z]{3}$")
    items: list[LineItem] = Field(min_length=1, max_length=50)


def usd(usage: Usage, tier: str) -> float:
    price_in, price_out = PRICE_PER_MTOK[tier]
    fresh = usage.input_tokens - usage.cached_tokens
    billed_in = fresh + usage.cached_tokens * CACHE_DISCOUNT
    return (billed_in * price_in + usage.output_tokens * price_out) / 1_000_000


@dataclass
class Extraction:
    declaration: Declaration | None
    spent_usd: float
    attempts: int
    error: str = ""


def repair(prompt: str, bad: str, err: ValidationError) -> str:
    problems = "; ".join(".".join(str(p) for p in e["loc"]) + ": " + e["msg"]
                         for e in err.errors())
    return (f"{prompt}\n\nThe previous answer failed schema validation: {problems}\n"
            f"Return the corrected JSON in full:\n{bad}")


def extract(doc: str, client: ModelClient, tier: str = "flash",
            budget_usd: float = 0.02) -> Extraction:
    schema = Declaration.model_json_schema()
    prompt = f"Return a declaration strictly following the schema. Document:\n{doc}"
    if count_tokens(prompt) > MAX_INPUT_TOKENS:
        return Extraction(None, 0.0, 0, "input_budget")
    spent = 0.0
    for attempt in (1, 2):
        reply = client.generate(prompt, schema=schema, max_output_tokens=MAX_OUTPUT_TOKENS)
        spent += usd(reply.usage, tier)
        if reply.finish_reason == "length":
            return Extraction(None, spent, attempt, "truncated")
        if reply.finish_reason == "refusal":
            return Extraction(None, spent, attempt, "refusal")
        try:
            return Extraction(Declaration.model_validate_json(reply.text), spent, attempt)
        except ValidationError as err:
            if attempt == 2 or spent > budget_usd:
                return Extraction(None, spent, attempt, "schema")
            prompt = repair(prompt, reply.text, err)
    return Extraction(None, spent, 2, "schema")


if __name__ == "__main__":
    doc = "TKL-000412 | DE | DAP | 8703.23 | passenger car | 2 pcs | 18400 EUR"
    bad = ('{"shipment_id": "TKL-000412", "origin": "DE", "incoterm": "DAP", "items": '
           '[{"hs_code": "870323", "description": "passenger car", '
           '"quantity": 2, "value_eur": 18400}]}')
    good = bad.replace("870323", "8703.23")
    client = FakeModel([bad, good])
    done = extract(doc, client)
    assert done.declaration is not None and done.attempts == 2
    assert done.declaration.items[0].hs_code == "8703.23"
    assert "items.0.hs_code" in client.prompts[1]    # the repair named the broken field
    assert done.spent_usd < 0.02
    typical = Usage(input_tokens=3_100, output_tokens=420, cached_tokens=1_800)
    assert round(usd(typical, "flash"), 5) == 0.00051
    assert usd(typical, "pro") > 8 * usd(typical, "flash")
    print(f"declaration assembled in {done.attempts} calls, "
          f"a typical document costs ${usd(typical, 'flash'):.5f}")
