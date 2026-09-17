import hashlib

CONFIG: dict[str, object] = {
    "model": "model-pro",                          # alias: веса за ним меняет поставщик
    "prompt": "Отвечай по руководствам и называй редакцию источника.",
    "index": "guidelines-live",                    # имя живого индекса, а не снимок
    "temperature": 0.2,
}
CHANGES: list[str] = []


def edit(key: str, value: object) -> None:
    CONFIG[key] = value                            # прежнее значение потеряно
    CHANGES.append(key)                            # ни времени, ни автора, ни значения


def fingerprint() -> str:
    raw = "|".join(f"{key}={CONFIG[key]}" for key in sorted(CONFIG))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


if __name__ == "__main__":
    friday = fingerprint()
    edit("prompt", "Кратко: доза, кратность, источник. Пример: «G-12, редакция 7, раздел 4.2».")
    edit("temperature", 0.0)
    edit("temperature", 0.2)                       # «вернули как было»
    # ночью переиндексация заменила содержимое guidelines-live, словарь этого не видит
    monday = fingerprint()
    assert monday != friday                        # поведение другое
    assert CONFIG["index"] == "guidelines-live"    # смена корпуса не оставила следа
    assert CHANGES == ["prompt", "temperature", "temperature"]      # когда и что именно, неизвестно
    assert "Отвечай по руководствам" not in str(CONFIG["prompt"])  # пятничный промпт не вернуть
    print("пятничное состояние потеряно, жалобу в 09:10 не с чем сопоставить")
