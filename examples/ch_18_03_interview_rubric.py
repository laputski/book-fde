from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean

BAR = 2.5                                # нижняя граница по каждому сигналу
DRIFT = 0.5                              # смещение, после которого нужна калибровка


class Signal(StrEnum):
    BUILDING = "построение"
    OPERATING = "эксплуатация"
    JUDGEMENT = "суждение с заказчиком"
    COMMUNICATION = "коммуникация"


ANCHORS: dict[Signal, tuple[str, str, str, str]] = {   # якоря для оценок 1, 2, 3, 4
    Signal.BUILDING: ("решение не работает", "работает на примере, границы не проверены",
                      "границы и ошибки обработаны, есть тест", "3 и качество измерено"),
    Signal.OPERATING: ("не знает, что было после выпуска", "описывает инцидент без причины",
                       "находит причину по трассам", "3 и меняет процесс"),
    Signal.JUDGEMENT: ("принимает любой объём", "видит конфликт, выбора не предлагает",
                       "переводит конфликт в выбор с ценой", "3 и сужает объём без потери доверия"),
    Signal.COMMUNICATION: ("адресат не понял", "понятно инженеру, не руководителю",
                           "понятно обоим, вывод в начале", "3 и глубина по реакции"),
}
STAGES = {"practical": Signal.BUILDING, "scenario": Signal.JUDGEMENT,
          "deep_dive": Signal.OPERATING, "collaboration": Signal.COMMUNICATION}


@dataclass(frozen=True)
class Score:
    candidate: str
    interviewer: str
    signal: Signal
    value: int
    evidence: str                        # наблюдение, к которому привязан якорь

    def __post_init__(self) -> None:
        if not 1 <= self.value <= len(ANCHORS[self.signal]):
            raise ValueError(f"оценка {self.value} вне шкалы 1–4")
        if not self.evidence.strip():
            raise ValueError("оценка без наблюдения не принимается")


def offsets(scores: list[Score]) -> dict[str, float]:
    """Среднее отклонение интервьюера от остальной панели на общих кандидатах."""
    items: defaultdict[tuple[str, Signal], dict[str, int]] = defaultdict(dict)
    for s in scores:
        items[(s.candidate, s.signal)][s.interviewer] = s.value
    deltas: defaultdict[str, list[float]] = defaultdict(list)
    for marks in items.values():
        for who, value in marks.items():
            others = [v for w, v in marks.items() if w != who]
            if others:                   # кандидата оценил один человек: сравнивать не с кем
                deltas[who].append(value - fmean(others))
    return {who: round(fmean(d), 2) for who, d in sorted(deltas.items())}


def profile(scores: list[Score], candidate: str,
            shift: dict[str, float] | None = None) -> dict[Signal, float]:
    shift = shift or {}
    per_signal: defaultdict[Signal, list[float]] = defaultdict(list)
    for s in scores:
        if s.candidate == candidate:
            per_signal[s.signal].append(s.value - shift.get(s.interviewer, 0.0))
    return {sig: round(fmean(v), 2) for sig, v in per_signal.items()}


def decide(scores: list[Score], candidate: str, drift: dict[str, float]) -> str:
    raw = profile(scores, candidate)
    if missing := [str(sig) for sig in Signal if sig not in raw]:
        return "нет решения: не измерено " + ", ".join(missing)
    adjusted = profile(scores, candidate, drift)
    if unstable := [str(sig) for sig in Signal if (raw[sig] >= BAR) != (adjusted[sig] >= BAR)]:
        return "перемерить: " + ", ".join(unstable)
    return "нанять" if min(raw.values()) >= BAR else "не нанимать"


if __name__ == "__main__":
    assert len(set(STAGES.values())) == len(STAGES) == len(Signal)   # этап = один сигнал
    panel = ["Анна", "Борис", "Вера", "Глеб"]
    calibration = [Score(rec, who, Signal.BUILDING, v, "запись упражнения")
                   for rec, values in (("rec-1", (2, 3, 2, 2)), ("rec-2", (3, 4, 3, 3)),
                                       ("rec-3", (1, 2, 1, 1)))
                   for who, v in zip(panel, values, strict=True)]
    offs = offsets(calibration)
    assert offs == {"Анна": -0.33, "Борис": 1.0, "Вера": -0.33, "Глеб": -0.33}
    drift = {who: o for who, o in offs.items() if abs(o) >= DRIFT}
    assert drift == {"Борис": 1.0}

    loop = [Score("К-41", "Борис", Signal.BUILDING, 3, "тест на границы есть, метрики нет"),
            Score("К-41", "Глеб", Signal.OPERATING, 3, "нашёл причину по трассе"),
            Score("К-41", "Вера", Signal.JUDGEMENT, 4, "предложил выбор с ценой"),
            Score("К-41", "Анна", Signal.COMMUNICATION, 3, "вывод в первой фразе"),
            Score("К-42", "Анна", Signal.BUILDING, 3, "границы обработаны"),
            Score("К-42", "Вера", Signal.JUDGEMENT, 3, "назвал цену объёма"),
            Score("К-42", "Анна", Signal.COMMUNICATION, 3, "понятно обоим")]
    assert decide(loop, "К-41", drift) == "перемерить: построение"
    assert decide(loop, "К-42", drift) == "нет решения: не измерено эксплуатация"
    loop.append(Score("К-42", "Глеб", Signal.OPERATING, 2, "инцидент без причины"))
    assert decide(loop, "К-42", drift) == "не нанимать"
    for bad in ((5, "наблюдение"), (3, " ")):
        try:
            Score("К-43", "Анна", Signal.BUILDING, *bad)
            raise AssertionError("недопустимая оценка принята")
        except ValueError:
            pass
    print("смещения панели:", offs, "· К-41:", decide(loop, "К-41", drift))
