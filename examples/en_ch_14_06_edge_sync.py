from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

EXPORT_FIELDS = ("plant", "line", "defect", "severity", "model_version", "ts")


@dataclass
class Outbox:
    """The plant's results wait for a transfer window; the id is derived from content."""
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)

    def put(self, record: dict[str, Any]) -> str:
        clean = {k: record[k] for k in EXPORT_FIELDS if k in record}
        raw = json.dumps(clean, sort_keys=True).encode("utf-8")
        rid = hashlib.sha256(raw).hexdigest()[:32]
        self.pending[rid] = clean
        return rid

    def flush(self, upload: Callable[[str, dict[str, Any]], None]) -> int:
        sent = 0
        for rid in sorted(self.pending):
            upload(rid, self.pending[rid])       # may break off at any record
            del self.pending[rid]                # removed only after acknowledgement
            sent += 1
        return sent


@dataclass
class CentralIntake:
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    lose_ack_at: int = 0                         # number of the call whose acknowledgement is lost
    calls: int = 0

    def upload(self, rid: str, record: dict[str, Any]) -> None:
        self.calls += 1
        self.rows.setdefault(rid, record)        # a repeat with the same id changes nothing
        if self.calls == self.lose_ack_at:
            raise ConnectionError("the transfer window closed before the acknowledgement")


@dataclass(frozen=True)
class Package:
    name: str
    version: int
    weights: bytes
    manifest: bytes                              # JSON: name, version, sha256 of the weights
    signature: bytes


def build(name: str, version: int, weights: bytes, key: bytes) -> Package:
    manifest = json.dumps({"name": name, "version": version,
                           "sha256": hashlib.sha256(weights).hexdigest()}).encode("utf-8")
    return Package(name, version, weights, manifest, hmac.new(key, manifest, "sha256").digest())


def verify(pkg: Package, key: bytes) -> str:
    """An empty string if the package is intact; otherwise the reason for refusal."""
    if not hmac.compare_digest(hmac.new(key, pkg.manifest, "sha256").digest(), pkg.signature):
        return "the manifest signature does not match"
    meta = json.loads(pkg.manifest)
    if meta["sha256"] != hashlib.sha256(pkg.weights).hexdigest():
        return "the weights hash does not match the manifest"
    if (meta["name"], meta["version"]) != (pkg.name, pkg.version):
        return "the manifest describes another package"
    return ""


@dataclass
class PlantRegistry:
    key: bytes
    evaluate: Callable[[Package], float]         # offline evaluation on the plant's reference set
    floor: float = 0.90
    tolerance: float = 0.01                      # allowed drop against the active version
    active: Package | None = None
    score: float = 0.0
    previous: list[Package] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def install(self, pkg: Package, now: float) -> bool:
        reason = verify(pkg, self.key)
        if not reason and self.active and pkg.version <= self.active.version:
            reason = f"version {pkg.version} is not newer than active {self.active.version}"
        score = self.evaluate(pkg) if not reason else 0.0
        if not reason and (score < self.floor or score < self.score - self.tolerance):
            reason = f"offline evaluation {score:.2f} fails the gate"
        if reason:
            self.log.append(f"{now:.0f} refused {pkg.name}:{pkg.version}: {reason}")
            return False
        if self.active:
            self.previous.append(self.active)
        self.active, self.score = pkg, score
        self.log.append(f"{now:.0f} active {pkg.name}:{pkg.version}")
        return True


if __name__ == "__main__":
    key = b"helix-release-key"
    scores = {b"w3": 0.93, b"w4-q4": 0.88, b"w5": 0.94}
    plant = PlantRegistry(key, evaluate=lambda p: scores[p.weights])
    assert plant.install(build("inspect-8b", 3, b"w3", key), now=100)
    v4 = build("inspect-8b", 4, b"w4-q4", key)
    tampered = Package(v4.name, v4.version, b"w4-patched", v4.manifest, v4.signature)
    assert not plant.install(tampered, now=200) and "hash" in plant.log[-1]
    assert not plant.install(v4, now=300) and "evaluation 0.88" in plant.log[-1]
    assert plant.install(build("inspect-8b", 5, b"w5", key), now=400)
    assert not plant.install(build("inspect-8b", 3, b"w3", key), now=500)   # rollback is explicit only
    assert plant.active is not None and plant.active.version == 5
    assert [p.version for p in plant.previous] == [3]

    outbox, intake = Outbox(), CentralIntake(lose_ack_at=2)
    for ts in (1, 2, 3, 3):                      # the last record repeats the third
        outbox.put({"plant": "P12", "line": "L3", "defect": "crack", "severity": 3,
                    "operator": "Ivanov", "model_version": 5, "ts": ts})
    assert len(outbox.pending) == 3
    try:
        outbox.flush(intake.upload)
    except ConnectionError:
        pass
    assert (len(intake.rows), len(outbox.pending)) == (2, 2)
    assert outbox.flush(intake.upload) == 2
    assert len(intake.rows) == 3 and not outbox.pending
    assert all("operator" not in row for row in intake.rows.values())
    print("package verified and evaluated offline, results delivered without duplicates or names")
