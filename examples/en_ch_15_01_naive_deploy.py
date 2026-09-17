import hashlib

CONFIG: dict[str, object] = {
    "model": "model-pro",                          # an alias: the provider changes the weights behind it
    "prompt": "Answer from the guidelines and name the edition of the source.",
    "index": "guidelines-live",                    # the name of a live index, not a snapshot
    "temperature": 0.2,
}
CHANGES: list[str] = []


def edit(key: str, value: object) -> None:
    CONFIG[key] = value                            # the previous value is gone
    CHANGES.append(key)                            # no time, no author, no value


def fingerprint() -> str:
    raw = "|".join(f"{key}={CONFIG[key]}" for key in sorted(CONFIG))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


if __name__ == "__main__":
    friday = fingerprint()
    edit("prompt", "Briefly: dose, frequency, source. Example: 'G-12, edition 7, section 4.2'.")
    edit("temperature", 0.0)
    edit("temperature", 0.2)                       # "put it back as it was"
    # overnight re-indexing replaced the contents of guidelines-live; the dictionary cannot see it
    monday = fingerprint()
    assert monday != friday                        # the behaviour is different
    assert CONFIG["index"] == "guidelines-live"    # the corpus change left no trace
    assert CHANGES == ["prompt", "temperature", "temperature"]      # when and what exactly: unknown
    assert "Answer from the guidelines" not in str(CONFIG["prompt"])  # Friday's prompt is lost
    print("Friday's state is lost; the 09:10 complaint has nothing to be matched against")
