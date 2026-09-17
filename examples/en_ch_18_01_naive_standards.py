STANDARDS = """Squad standards, revision 3 (wiki)
1. An engagement repository has an evaluation set and a release gate.
2. Every model call lands in a trace.
3. Prompts are versioned in the repository.
4. A release is described by a release bundle manifest."""


def check(repo: dict[str, str], team_confirmed: bool) -> bool:
    """The wiki check: the team confirmed that it has read the standards."""
    return team_confirmed and "standard" in repo.get("README.md", "").lower()


if __name__ == "__main__":
    repo = {
        "README.md": "We follow the squad standards, see the wiki.",
        "app.py": 'PROMPT = "You are a bank assistant. Answer briefly."',
    }
    assert check(repo, team_confirmed=True)                     # the "check" passes
    assert not any(path.startswith("evals/") for path in repo)  # 1: no evaluations
    assert "config/observability.json" not in repo              # 2: no tracing
    assert "PROMPT = " in repo["app.py"]                        # 3: prompt hard-coded
    assert "release/manifest.json" not in repo                  # 4: no manifest
    print("all 4 wiki rules broken, the check passes")
