"""Measure a Laya checkpoint (the stock model, or a fine-tuned folder) on the policies.

    python finetune/evaluate.py                          # the stock model
    python finetune/evaluate.py --checkpoint finetune/out/tuned --label tuned

Two measurements:
  1. the model alone on the held-out set (data/eval.jsonl): per policy, how many positives it finds
     (recall) and how many of its alarms are right (precision), at each policy's threshold
  2. the whole gate (rules + model, exactly as in the agent) on the hand-written cases in
     policy_cases.toml, which are never used for training: the same numbers `make test-policy` prints
"""
import argparse
import json
import os
import sys
import time

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "laya"))
sys.path.insert(0, os.path.join(ROOT, "agent"))
os.environ.setdefault("POLICY_CONFIG", os.path.join(ROOT, "policies.toml"))
import policy  # noqa: E402  the agent's own gate, so the result is the real one
import scoring  # noqa: E402


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip() and not line.startswith("#")]


def model_on_heldout(scorer, rows, policies):
    pairs = [(p.id, p.criterion) for p in policies]
    stats = {p.id: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for p in policies}
    for row in rows:
        scores = scorer.score([row["state"]["text"]], pairs)
        for p in policies:
            predicted, actual = scores[p.id] >= p.threshold, bool(row["expected"][p.id])
            key = ("t" if predicted == actual else "f") + ("p" if predicted else "n")
            stats[p.id][key] += 1
    return stats


def gate_on_cases(scorer, cases):
    """Decisions of the real gate, rules only and with this model, for every hand-written case."""
    saved = policy.model_scores
    policy.model_scores = lambda texts, policies: scorer.score(texts, [(p.id, p.criterion) for p in policies])
    out = []
    try:
        for c in cases:
            policy.LAYA_URL = ""
            rules = policy.check(c["text"])["action"]
            policy.LAYA_URL = "local-model"  # any non-empty value: model_scores is replaced above
            full = policy.check(c["text"])["action"]
            out.append({"kind": c["kind"], "expect": c["expect"], "rules": rules, "model": full, "text": c["text"]})
    finally:
        policy.model_scores = saved
    return out


def summarise(decisions, key):
    unsafe = [d for d in decisions if d["expect"] != "allow"]
    safe = [d for d in decisions if d["expect"] == "allow"]
    return {
        "exact": sum(d[key] == d["expect"] for d in decisions), "n": len(decisions),
        "missed": sum(d[key] == "allow" for d in unsafe), "unsafe": len(unsafe),
        "false_alarms": sum(d[key] != "allow" for d in safe), "safe": len(safe),
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", default="", help="a folder written by laya-train (default: the stock model)")
    ap.add_argument("--model", default="english", help="stock checkpoint when no --checkpoint: english or multilingual")
    ap.add_argument("--label", default="", help="name for this run in the output (default: stock or the folder name)")
    ap.add_argument("--eval", default=os.path.join(here, "data", "eval.jsonl"))
    ap.add_argument("--json", default="", help="also write the results to this file")
    args = ap.parse_args()
    label = args.label or (os.path.basename(os.path.normpath(args.checkpoint)) if args.checkpoint else "stock")

    scorer = scoring.Scorer(args.model, args.checkpoint)
    scorer.warm_up()
    result = {"label": label, "checkpoint": args.checkpoint or f"stock:{args.model}"}

    if os.path.exists(args.eval):
        started = time.time()
        rows = read_jsonl(args.eval)
        stats = model_on_heldout(scorer, rows, policy.POLICIES)
        result["heldout"] = stats
        print(f"\n[{label}] model alone on {len(rows)} held-out rows ({time.time() - started:.0f}s)")
        print(f"  {'policy':<24} {'found':>7} {'precision':>10}   tp  fp  fn  tn")
        for pid, s in stats.items():
            recall = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else float("nan")
            precision = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else float("nan")
            print(f"  {pid:<24} {recall:>7.0%} {precision:>10.0%}  {s['tp']:>3} {s['fp']:>3} {s['fn']:>3} {s['tn']:>3}")
    else:
        print(f"(no held-out file at {args.eval}: run finetune/make_dataset.py)")

    with open(os.path.join(ROOT, "policy_cases.toml"), "rb") as f:
        cases = tomllib.load(f)["cases"]
    decisions = gate_on_cases(scorer, cases)
    rules, model = summarise(decisions, "rules"), summarise(decisions, "model")
    result["gate"] = {"rules_only": rules, "with_model": model, "decisions": decisions}
    print(f"\n[{label}] the whole gate on the {len(cases)} hand-written cases (policy_cases.toml)")
    for name, s in (("rules only", rules), ("rules + model", model)):
        print(f"  {name:<14} exact {s['exact']}/{s['n']}   unsafe let through (misses) {s['missed']}/{s['unsafe']}"
              f"   safe flagged {s['false_alarms']}/{s['safe']}")
    for d in decisions:
        if d["model"] != d["expect"]:
            print(f"    {'MISS' if d['model'] == 'allow' else 'differs':<8} expected {d['expect']:<6} got {d['model']:<6} {d['text'][:70]}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
