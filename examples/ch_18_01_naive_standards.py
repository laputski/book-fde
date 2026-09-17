STANDARDS = """Стандарты squad, редакция 3 (вики)
1. В репозитории engagement есть оценочный набор и ворота релиза.
2. Каждый вызов модели попадает в трассу.
3. Промпты версионируются в репозитории.
4. Выпуск описан манифестом release bundle."""


def check(repo: dict[str, str], team_confirmed: bool) -> bool:
    """Проверка по вики: команда подтвердила, что прочитала стандарты."""
    return team_confirmed and "стандарт" in repo.get("README.md", "").lower()


if __name__ == "__main__":
    repo = {
        "README.md": "Работаем по стандартам squad, см. вики.",
        "app.py": 'PROMPT = "Ты ассистент банка. Отвечай кратко."',
    }
    assert check(repo, team_confirmed=True)                     # «проверка» пройдена
    assert not any(path.startswith("evals/") for path in repo)  # 1: оценок нет
    assert "config/observability.json" not in repo              # 2: трассировки нет
    assert "PROMPT = " in repo["app.py"]                        # 3: промпт зашит в код
    assert "release/manifest.json" not in repo                  # 4: манифеста нет
    print("нарушены все 4 правила из вики, проверка пройдена")
