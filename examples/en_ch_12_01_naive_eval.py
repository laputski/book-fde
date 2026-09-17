GOLD = {
    "contactless limit without a PIN": "50 €",
    "time to resolve a disputed payment": "up to 45 days",
    "fee for a SEPA transfer": "no fee",
    "time to reissue a card": "5 business days",
    "rate on the Plus deposit": "2.1 % a year",
    "cash withdrawal limit on a Classic card": "1 000 € a day",
    "contact-centre opening hours": "24/7",
    "where to get a statement": "in the app, Documents section",
    "how to block a card": "in the app or by phone",
    "documents for a mortgage": "ID, proof of income, contract",
}


def assistant(question: str) -> str:
    answers = dict(GOLD)
    answers["time to resolve a disputed payment"] = "A dispute is resolved within 45 days at most."
    return answers[question]


def accuracy() -> float:
    return sum(assistant(q) == gold for q, gold in GOLD.items()) / len(GOLD)


if __name__ == "__main__":
    score = accuracy()
    assert score == 0.9                     # a correct paraphrase is scored as a failure
    print("accuracy:", score)
