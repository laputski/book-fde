"""A naive engagement plan: a to-do list in a dict."""

PLAN = {
    "week 1": ["meet the stakeholders", "ask for data access"],
    "week 2": ["clarify the requirements", "pick a model"],
    "weeks 3-10": ["development", "a demo every two weeks"],
    "weeks 11-12": ["final demo", "handover"],
}

if __name__ == "__main__":
    tasks = [t for group in PLAN.values() for t in group]
    assert len(tasks) == 8
    assert all(isinstance(t, str) for t in tasks)   # a string with no owner or condition
    print(len(tasks), "items: no owner, no exit criterion, no gate")
