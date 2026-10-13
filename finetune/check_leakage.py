"""Check how close the test cases are to the training data.

    python finetune/check_leakage.py            # uses finetune/data/train.jsonl and policy_cases.toml

A test is only fair if the model has not effectively seen it. For every case in policy_cases.toml this
reports the share of its 4-word sequences that also occur in some training row (0% = nothing shared,
100% = a near-copy), and which training row is closest. Cases at or above the limit are flagged.
Training rows are generated from templates, so a high score usually means a test was modelled on a template.
"""
import argparse
import json
import os
import re
import sys

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
N = 4  # words per sequence


def grams(text):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i:i + N]) for i in range(max(0, len(words) - N + 1))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default=os.path.join(HERE, "data", "train.jsonl"))
    ap.add_argument("--cases", default=os.path.join(HERE, "..", "policy_cases.toml"))
    ap.add_argument("--limit", type=float, default=0.30, help="flag cases sharing at least this fraction (default 0.30)")
    args = ap.parse_args()

    with open(args.train, encoding="utf-8") as f:
        train = [json.loads(line)["state"]["text"] for line in f if line.strip()]
    train_grams = [(t, grams(t)) for t in train]
    with open(args.cases, "rb") as f:
        cases = tomllib.load(f)["cases"]

    flagged, by_kind = 0, {}
    for c in cases:
        g = grams(c["text"])
        best, best_text = 0.0, ""
        for text, tg in train_grams:
            share = len(g & tg) / len(g) if g else 0.0
            if share > best:
                best, best_text = share, text
        by_kind.setdefault(c["kind"], []).append(best)
        if best >= args.limit:
            flagged += 1
            print(f"{best:>5.0%}  [{c['kind']}] {c['text'][:70]}\n       closest training row: {best_text[:70]}")
    print(f"\n{flagged} of {len(cases)} cases share {args.limit:.0%} or more of their word sequences with a training row.")
    print("\nlargest overlap per kind (mean / max):")
    for kind, vals in by_kind.items():
        print(f"  {kind:<22} {sum(vals) / len(vals):>5.0%} / {max(vals):>5.0%}   ({len(vals)} cases)")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
