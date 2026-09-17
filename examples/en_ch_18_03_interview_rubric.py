from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean

BAR = 2.5                                # lower bound for every signal
DRIFT = 0.5                              # offset beyond which calibration is due


class Signal(StrEnum):
    BUILDING = "building"
    OPERATING = "operating"
    JUDGEMENT = "customer judgement"
    COMMUNICATION = "communication"


ANCHORS: dict[Signal, tuple[str, str, str, str]] = {   # anchors for scores 1, 2, 3, 4
    Signal.BUILDING: ("does not work", "works on the example, edges unchecked",
                      "edges and errors handled, tested", "3 plus quality measured"),
    Signal.OPERATING: ("unaware of life after release", "describes an incident, not its cause",
                       "finds the cause from traces", "3 plus changes the process"),
    Signal.JUDGEMENT: ("accepts any scope", "sees the conflict, offers no choice",
                       "turns the conflict into a priced choice", "3 plus narrows scope, keeps trust"),
    Signal.COMMUNICATION: ("the listener is lost", "clear to engineers, not to managers",
                           "clear to both, conclusion first", "3 plus depth set by the listener"),
}
STAGES = {"practical": Signal.BUILDING, "scenario": Signal.JUDGEMENT,
          "deep_dive": Signal.OPERATING, "collaboration": Signal.COMMUNICATION}


@dataclass(frozen=True)
class Score:
    candidate: str
    interviewer: str
    signal: Signal
    value: int
    evidence: str                        # the observation the anchor is tied to

    def __post_init__(self) -> None:
        if not 1 <= self.value <= len(ANCHORS[self.signal]):
            raise ValueError(f"score {self.value} outside the 1–4 scale")
        if not self.evidence.strip():
            raise ValueError("a score without an observation is not accepted")


def offsets(scores: list[Score]) -> dict[str, float]:
    """Mean deviation of an interviewer from the rest of the panel on shared candidates."""
    items: defaultdict[tuple[str, Signal], dict[str, int]] = defaultdict(dict)
    for s in scores:
        items[(s.candidate, s.signal)][s.interviewer] = s.value
    deltas: defaultdict[str, list[float]] = defaultdict(list)
    for marks in items.values():
        for who, value in marks.items():
            others = [v for w, v in marks.items() if w != who]
            if others:                   # scored by one person: nobody to compare with
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
        return "no decision: not measured " + ", ".join(missing)
    adjusted = profile(scores, candidate, drift)
    if unstable := [str(sig) for sig in Signal if (raw[sig] >= BAR) != (adjusted[sig] >= BAR)]:
        return "re-measure: " + ", ".join(unstable)
    return "hire" if min(raw.values()) >= BAR else "no hire"


if __name__ == "__main__":
    assert len(set(STAGES.values())) == len(STAGES) == len(Signal)   # stage = one signal
    panel = ["Anna", "Boris", "Vera", "Gleb"]
    calibration = [Score(rec, who, Signal.BUILDING, v, "exercise recording")
                   for rec, values in (("rec-1", (2, 3, 2, 2)), ("rec-2", (3, 4, 3, 3)),
                                       ("rec-3", (1, 2, 1, 1)))
                   for who, v in zip(panel, values, strict=True)]
    offs = offsets(calibration)
    assert offs == {"Anna": -0.33, "Boris": 1.0, "Vera": -0.33, "Gleb": -0.33}
    drift = {who: o for who, o in offs.items() if abs(o) >= DRIFT}
    assert drift == {"Boris": 1.0}

    loop = [Score("C-41", "Boris", Signal.BUILDING, 3, "edge test present, no metric"),
            Score("C-41", "Gleb", Signal.OPERATING, 3, "found the cause from a trace"),
            Score("C-41", "Vera", Signal.JUDGEMENT, 4, "offered a priced choice"),
            Score("C-41", "Anna", Signal.COMMUNICATION, 3, "conclusion in the first sentence"),
            Score("C-42", "Anna", Signal.BUILDING, 3, "edges handled"),
            Score("C-42", "Vera", Signal.JUDGEMENT, 3, "named the price of the scope"),
            Score("C-42", "Anna", Signal.COMMUNICATION, 3, "clear to both")]
    assert decide(loop, "C-41", drift) == "re-measure: building"
    assert decide(loop, "C-42", drift) == "no decision: not measured operating"
    loop.append(Score("C-42", "Gleb", Signal.OPERATING, 2, "incident without a cause"))
    assert decide(loop, "C-42", drift) == "no hire"
    for bad in ((5, "observation"), (3, " ")):
        try:
            Score("C-43", "Anna", Signal.BUILDING, *bad)
            raise AssertionError("an invalid score was accepted")
        except ValueError:
            pass
    print("panel offsets:", offs, "· C-41:", decide(loop, "C-41", drift))
