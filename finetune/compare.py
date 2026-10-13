"""Compare the runs in finetune/results/ side by side.

    python finetune/compare.py

For every results file: how the whole gate does on the hand-written cases, how the model alone does on the
held-out rows, and (for fine-tuned runs, from train_report.json) how confident it is compared with how often it
is right. A model whose mean confidence is far above its accuracy is over-confident.
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "results", "*.json"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name == "stock-44":
            continue
        d = load(path)
        gate = d["gate"]["with_model"]
        held = d.get("heldout", {})
        found = [s["tp"] / (s["tp"] + s["fn"]) for s in held.values() if s["tp"] + s["fn"]]
        prec = [s["tp"] / (s["tp"] + s["fp"]) for s in held.values() if s["tp"] + s["fp"]]
        fp = sum(s["fp"] for s in held.values())
        conf = acc = None
        ck = d.get("checkpoint", "")
        report = os.path.join(HERE, "..", ck, "train_report.json") if ck and not ck.startswith("stock") else ""
        if report and os.path.exists(report):
            after = load(report)["after"]
            conf, acc = after["mean_confidence"], after["accuracy"]
        rows.append((name, gate, found, prec, fp, acc, conf))

    print(f"{'run':<12} {'gate exact':>10} {'misses':>7} {'false alarms':>12} | {'held-out found':>14} {'precision':>9} {'fp':>3} | {'accuracy':>8} {'confidence':>10}")
    for name, g, found, prec, fp, acc, conf in rows:
        mean = lambda v: sum(v) / len(v) if v else float("nan")
        print(f"{name:<12} {g['exact']:>5}/{g['n']:<4} {g['missed']:>3}/{g['unsafe']:<3} {g['false_alarms']:>8}/{g['safe']:<3} | "
              f"{mean(found):>14.0%} {mean(prec):>9.0%} {fp:>3} | "
              f"{'' if acc is None else format(acc, '.1%'):>8} {'' if conf is None else format(conf, '.1%'):>10}")
    print("\n(found/precision are averaged over the four policies. accuracy and confidence are the model's own, on the held-out rows.)")


if __name__ == "__main__":
    main()
