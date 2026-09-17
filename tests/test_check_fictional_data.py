from __future__ import annotations

from check_fictional_data import violations


def test_reserved_numbers_and_domains_pass():
    text = ('"orion.msisdn": "+44 7700 900461", "+447700900461", "+44-7700-900111"\n'
            "drop@attacker.example, omar.h@mail.example, a@example.com, b@sub.example.org, c@x.test\n"
            "release nordbank-assist@2026.09.1 and a price of +20 000 tokens")
    assert violations(text) == []


def test_bait_plausible_real_phone_numbers():
    # the numbers the book carried until 2026-09-17
    text = 'msisdn = "+7 912 345-67-89"\nmessage = "+49 170 123 4567"'
    assert [line for line, _ in violations(text)] == [1, 2]


def test_bait_real_domain_and_lookalike_domain():
    text = "почта ivan@example.ru\nmail to ops@examplecorp.com"
    assert [what for _, what in violations(text)] == [
        "e-mail address 'ivan@example.ru'", "e-mail address 'ops@examplecorp.com'"]


def test_bait_number_outside_the_drama_range():
    assert len(violations("+44 7700 901234")) == 1
