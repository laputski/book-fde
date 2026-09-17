from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

type Repo = dict[str, str]              # file path -> content
type Rule = Callable[[Repo], list[str]]

RULES: dict[str, Rule] = {}
PINNED_MODEL = re.compile(r"[a-z0-9-]+@\d{8}")          # dated version, not an alias
SHA256 = re.compile(r"[0-9a-f]{64}")
INLINE_PROMPT = re.compile(r"^\s*\w*PROMPT\w*\s*=\s*[rf]?[\"']", re.M)


def rule(name: str) -> Callable[[Rule], Rule]:
    def register(fn: Rule) -> Rule:
        RULES[name] = fn
        return fn
    return register


def load(repo: Repo, path: str) -> dict:
    return json.loads(repo[path]) if path in repo else {}


@rule("evals")
def evals_gate(repo: Repo) -> list[str]:
    found: list[str] = []
    if not any(p.startswith("evals/") and p.endswith(".jsonl") for p in repo):
        found.append("no evaluation set evals/*.jsonl")
    if not load(repo, "evals/gate.json").get("thresholds"):
        found.append("release gate without thresholds in evals/gate.json")
    return found


@rule("tracing")
def tracing(repo: Repo) -> list[str]:
    cfg = load(repo, "config/observability.json").get("tracing", {})
    if not cfg.get("exporter"):
        return ["tracing not configured: no exporter"]
    return [] if 0 < cfg.get("sample_rate", 0) <= 1 else ["sample_rate outside (0, 1]"]


@rule("prompts")
def versioned_prompts(repo: Repo) -> list[str]:
    found = [f"{p}: prompt hard-coded" for p, text in sorted(repo.items())
             if p.endswith(".py") and INLINE_PROMPT.search(text)]
    found += [f"{p}: no version: line" for p, text in sorted(repo.items())
              if p.startswith("prompts/") and not text.startswith("version:")]
    return found


@rule("release")
def release_bundle(repo: Repo) -> list[str]:
    if "release/manifest.json" not in repo:
        return ["no manifest release/manifest.json"]
    m = load(repo, "release/manifest.json")
    found = [] if PINNED_MODEL.fullmatch(m.get("model", "")) else ["model not pinned to a version"]
    found += [f"{key} is not a content hash" for key in ("prompt_sha256", "config_sha256")
              if not SHA256.fullmatch(m.get(key, ""))]
    return found


def check(repo: Repo) -> dict[str, list[str]]:
    """Report: rule -> violations; a rule without violations is left out."""
    return {name: found for name, fn in RULES.items() if (found := fn(repo))}


if __name__ == "__main__":
    naive = {"README.md": "We follow the squad standards, see the wiki.",
             "app.py": 'PROMPT = "You are a bank assistant. Answer briefly."'}
    assert sorted(check(naive)) == ["evals", "prompts", "release", "tracing"]

    good = {
        "app.py": 'prompt = registry.load("prompts/answer.md")',
        "prompts/answer.md": "version: 7\nAnswer only from the sources.",
        "evals/cases.jsonl": '{"q": "card limit", "expected": "doc-12"}',
        "evals/gate.json": json.dumps({"thresholds": {"groundedness": 0.9}}),
        "config/observability.json": json.dumps(
            {"tracing": {"exporter": "otlp", "sample_rate": 0.2}}),
        "release/manifest.json": json.dumps({"model": "model-pro@20260301",
                                             "prompt_sha256": "a" * 64, "config_sha256": "b" * 64}),
    }
    assert check(good) == {}
    drifted = good | {"release/manifest.json": json.dumps(
        {"model": "model-pro-latest", "prompt_sha256": "a" * 64, "config_sha256": "main"})}
    assert check(drifted) == {"release": ["model not pinned to a version",
                                          "config_sha256 is not a content hash"]}
    squad = {"CF1": good, "CF4": drifted, "CF6": naive}
    failing = {cf: sorted(check(repo)) for cf, repo in squad.items() if check(repo)}
    assert failing == {"CF4": ["release"], "CF6": ["evals", "prompts", "release", "tracing"]}
    print(f"{len(RULES)} executable rules; violations: {failing}")
