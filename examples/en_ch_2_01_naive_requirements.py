NOTES = """- the assistant must be accurate
- answer fast
- integrate with the CRM
- bank-grade security
- take load off the agents"""

BULLETS = [line.removeprefix("- ") for line in NOTES.splitlines()]

if __name__ == "__main__":
    assert len(BULLETS) == 5
    assert not any(c.isdigit() for b in BULLETS for c in b)   # no threshold, volume or date
    print(len(BULLETS), "bullets and not one testable requirement")
