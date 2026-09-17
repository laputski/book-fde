from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

type Attr = str | int | float | bool

KEEP = frozenset({"orion.tenant", "orion.feature", "gen_ai.operation.name", "gen_ai.request.model",
                  "gen_ai.usage.input_tokens", "gen_ai.usage.cache_read.input_tokens",
                  "gen_ai.usage.output_tokens", "orion.cost_usd", "orion.duration_s", "orion.ttft_s",
                  "error.type"})
PSEUDONYMIZE = frozenset({"orion.user", "orion.msisdn"})
REDACT = frozenset({"gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.tool.call.arguments"})
NEVER = frozenset({"http.request.header.authorization", "orion.cdr", "orion.intercept_ref"})

PATTERNS = (
    (re.compile(r"\+?\d[\d\s()-]{8,}\d"), "<phone>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "<iban>"),
)


def redact(text: str) -> str:
    for pattern, placeholder in PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


@dataclass(frozen=True)
class Policy:
    key: bytes                      # from the secret store; destroying the key anonymises the archive
    content_rate: float = 0.01      # share of traces whose redacted content is kept

    def pseudonym(self, value: str) -> str:
        canonical = re.sub(r"[\s()-]", "", value)
        return hmac.new(self.key, canonical.encode(), hashlib.blake2b).hexdigest()[:16]

    def keeps_content(self, trace_id: str) -> bool:
        """The decision covers the whole trace and is the same in every process."""
        digest = hashlib.blake2b(trace_id.encode(), digest_size=8).digest()
        return int.from_bytes(digest) / 2**64 < self.content_rate

    def apply(self, trace_id: str, attrs: dict[str, Attr]) -> tuple[dict[str, Attr], dict[str, str]]:
        record: dict[str, Attr] = {}
        content: dict[str, str] = {}
        for k, v in attrs.items():
            if k in KEEP:
                record[k] = v
            elif k in PSEUDONYMIZE:
                record[k] = self.pseudonym(str(v))
            elif k in REDACT and self.keeps_content(trace_id):
                content[k] = redact(str(v))
            # everything else is dropped: NEVER, unknown keys and content outside the sample
        return record, content


if __name__ == "__main__":
    assert not NEVER & (KEEP | PSEUDONYMIZE | REDACT)
    policy = Policy(key=b"orion-logs-2026-09")
    span: dict[str, Attr] = {
        "orion.tenant": "consumer", "orion.feature": "agent_assist", "orion.cost_usd": 0.001307,
        "orion.duration_s": 2.3, "gen_ai.usage.output_tokens": 180,
        "orion.user": "u-5f2a", "orion.msisdn": "+44 7700 900461",
        "gen_ai.input.messages": "My number is +44 7700 900461, email ivan@mail.example. Why were 300 roubles charged?",
        "http.request.header.authorization": "Bearer eyJhbGciOiJSUzI1NiJ9", "debug.prompt_dump": "…",
    }
    ids = [f"trace-{i:05d}" for i in range(20_000)]
    sampled = next(t for t in ids if policy.keeps_content(t))
    unsampled = next(t for t in ids if not policy.keeps_content(t))

    record, content = policy.apply(sampled, span)
    assert record["orion.cost_usd"] == 0.001307 and record["orion.duration_s"] == 2.3   # price and time intact
    assert record["orion.msisdn"] == policy.pseudonym("+447700900461")                    # joinable with the key
    assert record["orion.msisdn"] != hashlib.sha256(b"+447700900461").hexdigest()[:16]   # and not brute-forceable
    assert "Bearer" not in str(record) and "debug.prompt_dump" not in record
    text = content["gen_ai.input.messages"]
    assert "<phone>" in text and "<email>" in text and "300 roubles" in text
    assert policy.apply(unsampled, span)[1] == {} and "orion.cost_usd" in policy.apply(unsampled, span)[0]
    share = sum(map(policy.keeps_content, ids)) / len(ids)
    assert 0.008 < share < 0.012
    print(f"logged: {len(record)} attributes of {len(span)}, content: {share:.1%} of traces, redacted")
