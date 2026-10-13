"""Try different decision thresholds on one checkpoint, scoring each text only once.

    python finetune/threshold_sweep.py --checkpoint finetune/out/ce-ls10 --thresholds 0.2,0.3,0.4,0.5,0.6

For each row of the output, every "local" policy's threshold is set to that value. Policies that block
(credentials) keep their own, stricter threshold: its rules do most of the work, and lowering it would
flag harmless questions about passwords. For each threshold it prints the whole gate on the
hand-written cases and the model alone on the held-out rows. This only makes sense for a calibrated model: a
saturated one (probabilities near 0 or 1) gives the same answers at every threshold.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate  # noqa: E402  (also puts agent/ and laya/ on the path)
import policy  # noqa: E402
import scoring  # noqa: E402

try:
    import tomllib
except ImportError:
    import tomli as tomllib


class CachedScorer:
    """Wraps a Scorer so that each (texts, policies) pair is scored once, whatever the threshold."""

    def __init__(self, scorer):
        self.scorer, self.cache = scorer, {}

    def score(self, texts, policies):
        key = (tuple(texts), tuple(policies))
        if key not in self.cache:
            self.cache[key] = self.scorer.score(texts, policies)
        return self.cache[key]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", default="")
    ap.add_argument("--model", default="english")
    ap.add_argument("--thresholds", default="0.2,0.3,0.4,0.5,0.6")
    ap.add_argument("--eval", default=os.path.join(HERE, "data", "eval.jsonl"))
    args = ap.parse_args()

    scorer = CachedScorer(scoring.Scorer(args.model, args.checkpoint))
    scorer.scorer.warm_up()
    rows = evaluate.read_jsonl(args.eval)
    with open(os.path.join(HERE, "..", "policy_cases.toml"), "rb") as f:
        cases = tomllib.load(f)["cases"]
    original = {p.id: p.threshold for p in policy.POLICIES}

    print(f"{'threshold':>9} | {'gate exact':>10} {'misses':>7} {'false alarms':>12} | {'held-out found':>14} {'precision':>9} {'fp':>3}")
    for th in [float(x) for x in args.thresholds.split(",")]:
        for p in policy.POLICIES:
            if p.action != "block":
                p.threshold = th
        decisions = evaluate.gate_on_cases(scorer, cases)
        g = evaluate.summarise(decisions, "model")
        stats = evaluate.model_on_heldout(scorer, rows, policy.POLICIES)
        found = [s["tp"] / (s["tp"] + s["fn"]) for s in stats.values() if s["tp"] + s["fn"]]
        prec = [s["tp"] / (s["tp"] + s["fp"]) for s in stats.values() if s["tp"] + s["fp"]]
        fp = sum(s["fp"] for s in stats.values())
        print(f"{th:>9.2f} | {g['exact']:>5}/{g['n']:<4} {g['missed']:>3}/{g['unsafe']:<3} {g['false_alarms']:>8}/{g['safe']:<3} | "
              f"{sum(found) / len(found):>14.0%} {sum(prec) / len(prec):>9.0%} {fp:>3}")
    for p in policy.POLICIES:
        p.threshold = original[p.id]


if __name__ == "__main__":
    main()
