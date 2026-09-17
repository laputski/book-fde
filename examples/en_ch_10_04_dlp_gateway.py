from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class InfoType(StrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    IBAN = "IBAN"
    CITIZEN_ID = "CITIZEN_ID"


PATTERNS = {
    InfoType.EMAIL: re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    InfoType.PHONE: re.compile(r"\+\d{2}(?:[ -]?\d{2,4}){3,4}\b"),
    InfoType.IBAN: re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
    InfoType.CITIZEN_ID: re.compile(r"\bNG-\d{6}-\d\b"),       # a fictional format with a check digit
}


def iban_valid(value: str) -> bool:
    compact = value.replace(" ", "")
    digits = "".join(str(int(ch, 36)) for ch in compact[4:] + compact[:4])
    return int(digits) % 97 == 1


def citizen_id_valid(value: str) -> bool:
    return sum(int(d) for d in value[3:9]) % 10 == int(value[-1])


VALIDATORS: dict[InfoType, Callable[[str], bool]] = {
    InfoType.IBAN: iban_valid, InfoType.CITIZEN_ID: citizen_id_valid}


@dataclass(frozen=True)
class Finding:
    info_type: InfoType
    start: int
    end: int
    fingerprint: str        # a hash of the value: the finding can be logged without the data


def detect(text: str) -> list[Finding]:
    found: list[Finding] = []
    for info_type, regex in PATTERNS.items():
        check = VALIDATORS.get(info_type)
        for m in regex.finditer(text):
            if check is not None and not check(m.group()):
                continue                                        # looks like an IBAN, is not one
            fingerprint = hashlib.sha256(m.group().encode()).hexdigest()[:12]
            found.append(Finding(info_type, m.start(), m.end(), fingerprint))
    found.sort(key=lambda f: (f.start, -f.end))
    kept: list[Finding] = []
    for f in found:
        if not kept or f.start >= kept[-1].end:
            kept.append(f)
    return kept


@dataclass
class EgressResult:
    text: str
    findings: list[Finding]
    blocked: bool


@dataclass
class DlpGateway:
    """Everything that leaves the perimeter passes here; the substitution table stays inside."""
    redact_for: frozenset[str]          # destinations where de-identified text is acceptable
    vault: dict[str, str] = field(default_factory=dict)

    def egress(self, text: str, destination: str) -> EgressResult:
        findings = detect(text)
        if findings and destination not in self.redact_for:
            return EgressResult("", findings, blocked=True)
        parts: list[str] = []
        counts: dict[InfoType, int] = {}
        cursor = 0
        for f in findings:
            counts[f.info_type] = counts.get(f.info_type, 0) + 1
            token = f"[{f.info_type}_{counts[f.info_type]}]"
            self.vault[token] = text[f.start:f.end]
            parts += [text[cursor:f.start], token]
            cursor = f.end
        parts.append(text[cursor:])
        return EgressResult("".join(parts), findings, blocked=False)

    def restore(self, text: str) -> str:
        return re.sub(r"\[[A-Z_]+_\d+\]", lambda m: self.vault.get(m.group(), m.group()), text)


if __name__ == "__main__":
    gateway = DlpGateway(redact_for=frozenset({"model-endpoint-eu"}))
    message = ("Omar Haddad, omar.h@mail.example, +44 7700 900 461, IBAN DE89 3704 0044 0532 0130 00, "
               "NG-120345-5: why has my benefit not arrived? Letter number GB00 0000 0000 0000 00.")
    out = gateway.egress(message, "model-endpoint-eu")
    assert [f.info_type for f in out.findings] == [
        InfoType.EMAIL, InfoType.PHONE, InfoType.IBAN, InfoType.CITIZEN_ID]
    assert "@" not in out.text and "DE89" not in out.text and "GB00 0000" in out.text
    assert "Omar Haddad" in out.text                        # a name is beyond a regular expression
    assert all(message[f.start:f.end] not in repr(f) for f in out.findings)
    reply = "The payment to account [IBAN_1] is scheduled, a letter went to [EMAIL_1]."
    assert "DE89 3704" in gateway.restore(reply) and "omar.h@" in gateway.restore(reply)
    blocked = gateway.egress(message, "analytics-export")
    assert blocked.blocked and blocked.text == ""
    print("findings:", len(out.findings), "·", out.text[:48], "…")
