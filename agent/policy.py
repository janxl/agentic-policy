"""Policy gate: check a request against data policies BEFORE it can be sent to a public LLM.

    check(text) -> {"action": "allow" | "local" | "block", "hits": [...], "engine": ..., ...}

Two kinds of check, cheapest first:
  rules   exact checks in plain code (regular expressions, a watchlist of names). Always on.
  model   a small local decision model (Laya) answers one yes/no question per policy, which catches
          paraphrased cases that rules cannot see. Used when LAYA_URL is set.

The gate fails closed: if the model is unreachable, or the text is too long to screen in full, the
request goes to the local model instead of the public one. Only the standard library is used.
"""
import json
import logging
import os
import re
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("policy")

SEVERITY = {"allow": 0, "local": 1, "block": 2}
LAYA_URL = os.environ.get("LAYA_URL", "").rstrip("/")
POLICY_CONFIG = os.environ.get("POLICY_CONFIG", "/config/policies.toml")
ENGINE_TIMEOUT = float(os.environ.get("LAYA_TIMEOUT", "15"))
LOG_LAYA = os.environ.get("LOG_LAYA", "true").strip().lower() in ("1", "true", "yes", "on")  # log what is sent to / received from the decision model
# The decision model reads a few hundred tokens at a time: longer text is screened in overlapping
# windows, and anything beyond MAX_CHUNKS windows is treated as "too long to screen".
CHUNK_CHARS, CHUNK_OVERLAP, MAX_CHUNKS = 1200, 150, 12


@dataclass
class Policy:
    id: str
    title: str
    action: str
    criterion: str = ""
    message: str = ""
    threshold: float = 0.6
    patterns: list = field(default_factory=list)   # compiled regular expressions
    watchlist: list = field(default_factory=list)  # names, matched as whole words, any case


def load(path: str | None = None) -> tuple[dict, list[Policy]]:
    """(settings, policies) from policies.toml. A missing file means no policies: everything is allowed."""
    try:
        with open(path or POLICY_CONFIG, "rb") as f:
            cfg = tomllib.load(f)
    except FileNotFoundError:
        return {"threshold": 0.6, "on_engine_error": "local"}, []
    settings = {"threshold": 0.6, "on_engine_error": "local", **cfg.get("settings", {})}
    policies = []
    for p in cfg.get("policies", []):
        if p.get("action") not in ("local", "block"):
            raise ValueError(f"policy {p.get('id')!r}: action must be 'local' or 'block'")
        policies.append(Policy(
            id=p["id"], title=p.get("title", p["id"]), action=p["action"],
            criterion=p.get("criterion", ""), message=p.get("message", ""),
            threshold=float(p.get("threshold", settings["threshold"])),
            patterns=[re.compile(x) for x in p.get("patterns", [])],
            watchlist=list(p.get("watchlist", [])),
        ))
    return settings, policies


SETTINGS, POLICIES = load()


# ---------------------------------------------------------------- rules

def rule_matches(text: str, policy: Policy) -> str | None:
    """What matched, in words that do not repeat the sensitive text; None if nothing did."""
    for pat in policy.patterns:
        if pat.search(text):
            return "pattern"
    for name in policy.watchlist:
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
            return "watchlist"
    return None


# ---------------------------------------------------------------- the decision model

def chunks(text: str) -> list[str]:
    """Overlapping windows on whitespace, so each fits the decision model's input limit."""
    if len(text) <= CHUNK_CHARS:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):  # cut at a space, not mid-word
            space = text.rfind(" ", start + CHUNK_CHARS // 2, end)
            end = space if space != -1 else end
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return out


def model_scores(texts: list[str], policies: list[Policy]) -> dict[str, float]:
    """Probability per policy id that the text breaches it (the highest across the windows)."""
    payload = {
        "texts": texts,
        "policies": [{"id": p.id, "criterion": p.criterion} for p in policies],
    }
    if LOG_LAYA:
        log.info("decision model request\n%s", json.dumps(payload, indent=2, ensure_ascii=False))
    req = urllib.request.Request(
        f"{LAYA_URL}/score", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=ENGINE_TIMEOUT) as resp:
        answer = json.loads(resp.read())
    if LOG_LAYA:
        log.info("decision model response\n%s", json.dumps(answer, indent=2))
    return {k: float(v) for k, v in answer["scores"].items()}


# ---------------------------------------------------------------- the decision

def check(text: str, policies: list[Policy] | None = None, settings: dict | None = None) -> dict:
    policies = POLICIES if policies is None else policies
    settings = SETTINGS if settings is None else settings
    started = time.time()
    hits: dict[str, dict] = {}
    scores: dict[str, float] = {}

    # 1. rules
    for p in policies:
        how = rule_matches(text, p)
        if how:
            hits[p.id] = {"score": 1.0, "source": "rule", "match": how}
            scores[p.id] = 1.0

    # 2. the decision model, for policies that have a criterion and no hit yet. If a rule already
    #    says "block" there is nothing the model could change, so skip it.
    engine, note = "rules-only", ""
    already_block = any(SEVERITY[next(p.action for p in policies if p.id == i)] == 2 for i in hits)
    pending = [p for p in policies if p.criterion and p.id not in hits]
    if LAYA_URL and pending and not already_block:
        windows = chunks(text)
        if len(windows) > MAX_CHUNKS:
            engine, note = "too-long", f"too long to screen in full ({len(text)} characters)"
        else:
            try:
                got = model_scores(windows, pending)
                engine = "laya"
                for p in pending:
                    s = got.get(p.id, 0.0)
                    scores[p.id] = s
                    if s >= p.threshold:
                        hits[p.id] = {"score": s, "source": "model"}
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
                engine, note = "unavailable", f"decision model unreachable ({type(e).__name__})"
                log.warning("policy engine error: %s", e)
    elif LAYA_URL:
        engine = "laya"  # nothing left for the model to decide

    by_id = {p.id: p for p in policies}
    action = "allow"
    for pid in hits:
        if SEVERITY[by_id[pid].action] > SEVERITY[action]:
            action = by_id[pid].action
    if engine in ("unavailable", "too-long"):  # fail closed
        fallback = settings.get("on_engine_error", "local")
        if SEVERITY[fallback] > SEVERITY[action]:
            action = fallback

    return {
        "action": action,
        "engine": engine,
        "note": note,
        "hits": [
            {"policy": pid, "title": by_id[pid].title, "action": by_id[pid].action, **info}
            for pid, info in sorted(hits.items(), key=lambda kv: -kv[1]["score"])
        ],
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "ms": round((time.time() - started) * 1000),
    }


def explain(decision: dict, policies: list[Policy] | None = None) -> str:
    """One sentence for the user about what the gate did and why."""
    policies = POLICIES if policies is None else policies
    by_id = {p.id: p for p in policies}
    hits = decision["hits"]
    if decision["action"] == "block":
        top = next((h for h in hits if h["action"] == "block"), None)
        return (by_id[top["policy"]].message if top and by_id[top["policy"]].message else
                "This request breaches a data policy, so it was not sent to any model.")
    if decision["action"] == "local":
        if hits:
            names = ", ".join(h["title"].lower() for h in hits)
            return f"Policy match ({names}): using the local model, so this stays on this machine."
        return f"Could not screen this request ({decision['note']}): using the local model to be safe."
    return ""
