"""Test the policy gate on synthetic requests (policy_cases.toml). Runs inside the agent pod (see test-policy.sh).

For every case it shows what the gate decided, twice: with plain rules only (the baseline) and with
the decision model on top. The report is the point: it shows what the model adds, and above all
which unsafe requests still get through ("misses"), which is the number that matters.

Exit code: non-zero only if the plain-rules baseline fails a case the rules are meant to handle
(safe requests, traps, credentials, and names on the watchlists). The model's results are reported,
not asserted, because they are exactly what is being measured.
"""
import os
import sys
import tomllib
from collections import defaultdict

# In the pod the script arrives on stdin (no __file__) and policy.py sits in the working directory;
# on a laptop it is run from a checkout of the repo.
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(HERE, "..", "agent"))
import policy  # noqa: E402

CASES_FILE = os.environ.get("POLICY_CASES", "/config/policy_cases.toml")
if not os.path.exists(CASES_FILE):
    CASES_FILE = os.path.join(HERE, "..", "policy_cases.toml")
RULE_KINDS = {"safe", "trap", "credentials", "customer", "project"}  # the rules alone should get these right

with open(CASES_FILE, "rb") as f:
    cases = tomllib.load(f)["cases"]

model_url = policy.LAYA_URL
print(f"policies: {[p.id for p in policy.POLICIES]}   decision model: {model_url or 'not configured (rules only)'}\n")


def decide(text, with_model):
    policy.LAYA_URL = model_url if with_model else ""
    return policy.check(text)


rows = []
for c in cases:
    base = decide(c["text"], with_model=False)
    full = decide(c["text"], with_model=True) if model_url else base
    rows.append((c, base, full))
policy.LAYA_URL = model_url

print(f"{'kind':<22} {'expect':<6} {'rules':<6} {'+model':<6} {'ms':>5}  request")
for c, base, full in rows:
    flag = "" if full["action"] == c["expect"] else "  <-- " + ("MISS" if full["action"] == "allow" else "differs")
    print(f"{c['kind']:<22} {c['expect']:<6} {base['action']:<6} {full['action']:<6} {full['ms']:>5}  {c['text'][:62]}{flag}")


def tally(index):
    unsafe = [r for r in rows if r[0]["expect"] != "allow"]
    safe = [r for r in rows if r[0]["expect"] == "allow"]
    out = rows
    exact = sum(r[index]["action"] == r[0]["expect"] for r in out)
    missed = sum(r[index]["action"] == "allow" for r in unsafe)
    false_alarm = sum(r[index]["action"] != "allow" for r in safe)
    return exact, len(out), missed, len(unsafe), false_alarm, len(safe)


print()
for label, idx in (("rules only", 1), ("rules + model", 2)):
    exact, n, missed, n_unsafe, fa, n_safe = tally(idx)
    print(f"{label:<14} exact: {exact}/{n}   unsafe requests let through (MISSES): {missed}/{n_unsafe}   safe requests flagged: {fa}/{n_safe}")

by_kind = defaultdict(lambda: [0, 0, 0])
for c, base, full in rows:
    k = by_kind[c["kind"]]
    k[0] += 1
    k[1] += base["action"] == c["expect"]
    k[2] += full["action"] == c["expect"]
print("\nby kind (correct, rules only / with model):")
for kind, (n, b, f) in by_kind.items():
    print(f"   {kind:<22} {b}/{n}   {f}/{n}")

failures = [(c, base) for c, base, _ in rows if c["kind"] in RULE_KINDS and base["action"] != c["expect"]]
print()
if failures:
    for c, base in failures:
        print(f"FAIL  rules baseline: expected {c['expect']}, got {base['action']}: {c['text'][:70]}")
    sys.exit(1)
print("PASS  the plain-rules baseline handles every case it is meant to")
