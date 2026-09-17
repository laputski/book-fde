BOXES = ["Portal", "Agent", "LLM", "Vector DB", "CRM", "Monitoring"]
ARROWS = [("Portal", "Agent"), ("Agent", "LLM"), ("Agent", "Vector DB"),
          ("Agent", "CRM"), ("Agent", "Monitoring")]


def impact(change: str) -> set[str]:
    """What does a changed requirement touch? The diagram contains only names and arrows."""
    hit = {box for box in BOXES if box.lower() in change.lower()}
    for source, target in ARROWS:
        if source in hit:
            hit.add(target)
    return hit


if __name__ == "__main__":
    assert impact("resident data must not leave the country") == set()   # no box names the driver
    assert impact("swap the LLM for a cheaper one") == {"LLM"}             # the cost of the swap is unknown
    assert len(BOXES) == 6 and len(ARROWS) == 5
    print("six boxes, five arrows, not a single decision")
