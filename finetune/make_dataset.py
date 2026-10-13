"""Generate a synthetic, labelled dataset for fine-tuning the decision model on the policies.

    python finetune/make_dataset.py            # writes finetune/data/train.jsonl and eval.jsonl

Three tiers keep the result honest:
  train  built from one set of phrasings
  eval   built from DIFFERENT phrasings, so overfitting to the templates shows up as a gap
  test   policy_cases.toml: written by hand, never used for training (see evaluate.py)

Everything is invented: companies, sites and secrets are made up (the "secrets" are random strings).
Each row is one request with a true/false label for every policy, in the format `laya-train` reads:
    {"state": {"text": ...}, "questions": {policy_id: {...}}, "expected": {policy_id: true|false}}
"""
import argparse
import json
import os
import random
import string
import sys

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "laya"))
import scoring  # noqa: E402  (shared with the server, so training uses the exact question wording)

PLACES = ["Tamworth", "Wagga Wagga", "Dubbo", "Moree", "Port Augusta", "Collinsville", "Mildura", "Bendigo",
          "Latrobe Valley", "Gladstone", "Broken Hill", "Orange", "Whyalla", "Kogan Creek", "Murray Bridge"]
TECH = ["battery", "solar farm", "wind farm", "pumped hydro scheme", "gas peaker", "transmission upgrade"]
WHO = ["a data centre operator", "our largest retail customer", "the developer", "a steelmaker we supply",
       "the aluminium smelter", "a hyperscaler client", "the council", "a mining customer", "the landowner",
       "our biggest industrial offtaker"]
NAMES = ["Harbour Grid Ltd", "Southern Ridge Energy", "Kelvin Foods", "Redgum Mining", "Ironbark Retail",
         "Silverline Steel", "Coastal Cold Storage", "Bellbird Pastoral", "Marlin Data", "Tallowood Paper"]
TERMS = ["a five-year PPA", "a connection agreement", "a revised tariff", "a take-or-pay clause",
         "a 3% price escalator", "a capacity charge", "a termination right", "a volume discount",
         "an exclusivity period", "a $/MWh price"]
UNITS = ["Cobalt Creek", "Mallee Flat", "Saltbush", "Greywater", "Pinnacle Hill", "Eastgate", "Wattle Plains"]
REGIONS = ["NSW", "Victoria", "Queensland", "South Australia", "Tasmania"]
PERIODS = ["last quarter", "last month", "last year", "this week", "over summer"]
MECHANICS = ["cap contracts", "swaps", "bid stacks", "rebidding", "frequency control markets",
             "settlement residues", "demand response", "scheduled loads"]
TOPICS = ["wholesale electricity prices", "battery storage", "demand response", "frequency control services",
          "renewable energy certificates", "grid connections", "transmission planning", "rooftop solar",
          "market price caps", "capacity markets", "curtailment", "hydrogen electrolysers"]


def mw(r):
    return r.choice([50, 80, 100, 150, 200, 250, 300, 400, 500])


def when(r):
    return r.choice(["next month", "in Q3", "by March", "before the end of the financial year",
                     "in the first half of next year", "later this quarter"])


def money(r):
    return r.choice([62, 75, 82, 95, 110, 140, 180, 250, 300])


def secret(r):
    """An invented secret in one of several common formats. Random strings, never real credentials."""
    def rnd(n, alphabet=string.ascii_letters + string.digits):
        return "".join(r.choice(alphabet) for _ in range(n))
    kind = r.choice(["anthropic", "openai", "github", "aws", "password", "dburl", "bearer", "slack", "pem"])
    if kind == "anthropic":
        return f"sk-ant-api03-{rnd(30, string.ascii_letters + string.digits + '_-')}"
    if kind == "openai":
        return f"sk-{rnd(32)}"
    if kind == "github":
        return f"ghp_{rnd(36)}"
    if kind == "aws":
        return "AKIA" + rnd(16, string.ascii_uppercase + string.digits)
    if kind == "password":
        return r.choice(["password", "pwd", "passwd"]) + r.choice([": ", " = ", " is "]) + rnd(5) + r.choice("!@#$%") + rnd(3)
    if kind == "dburl":
        return f"postgres://{r.choice(['admin', 'svc', 'reporting'])}:{rnd(10)}@db.internal:5432/{r.choice(['prod', 'billing'])}"
    if kind == "bearer":
        return f"Bearer {rnd(40, string.ascii_letters + string.digits + '._-')}"
    if kind == "slack":
        return f"xoxb-{rnd(10, string.digits)}-{rnd(24)}"
    return "-----BEGIN RSA PRIVATE KEY----- " + rnd(24) + " -----END RSA PRIVATE KEY-----"


# ---------------------------------------------------------------- phrasings: one list for train, a different one for eval
# {w} a counterparty (described or named) {t} contract terms {p} place {mw} capacity {when} timing {tech} technology
# {m} money per MWh {s} a secret {topic} a general topic {u} an asset {reg} a region {per} a past period {mech} a market mechanism

SAFE = {
    "train": [
        "Explain how {topic} work in the electricity market.",
        "What are the main risks of {topic}?",
        "Write a short summary of {topic} for a new starter.",
        "Give me three questions to ask a supplier about {topic}.",
        "Convert {mw} MW to kilowatts and explain the steps.",
        "Rewrite this politely: the report is late and we need it today.",
        "Write a Python function that sorts a list of dictionaries by a key.",
        "Draft a friendly out-of-office message for next week.",
        "What is the difference between a PPA and a spot-market contract?",
        "Suggest a structure for a ten-minute presentation on {topic}.",
        "Translate 'the substation is offline for maintenance' into French.",
        "How should I prepare for a job interview in the energy sector?",
    ],
    "eval": [
        "Could you give me an overview of {topic}?",
        "Why do people care about {topic}?",
        "Help me write a regular expression that matches an Australian postcode.",
        "Put together an agenda for a one-hour team meeting about {topic}.",
        "I am new to the industry. What should I read about {topic}?",
        "What does MWh stand for and how is it different from MW?",
        "Tidy up this sentence: the meeting got moved to thursday afternoon sorry",
        "Create a checklist for a site visit to a {tech}.",
        "Explain the difference between a battery's power rating and its energy capacity.",
        "Write a short poem about a windy day in {p}.",
    ],
}

HARD_NEGATIVE = {  # topics that sound sensitive but are not: each is false for every policy
    "train": [
        "How should a team store API keys and passwords safely?",
        "Explain what a bearer token is, in plain English.",
        "Write a press release for the {mw} MW {tech} we have just announced at {p}.",
        "Our {mw} MW {tech} at {p} was announced publicly last year. Draft a short update for the website.",
        "What is a good way to approach contract negotiations in general?",
        "Give me tips for managing a difficult customer relationship.",
        "How do futures contracts help a generator hedge price risk?",
        "What is a sensible way to structure a project plan for a new {tech}?",
        "Please remind users that their password must be at least twelve characters.",
        "Describe how electricity retailers typically price a fixed-rate plan.",
        "Explain how {mech} work in simple terms.",
        "What happened to {reg} wholesale prices {per}? Use public data.",
        "Give me a generic example of how a trader might hedge a {mw} MW exposure. Make up the numbers.",
        "Why do prices in {reg} spike in the evening?",
        "Write a short quiz on {mech} for a training session.",
    ],
    "eval": [
        "What is the best way to rotate credentials in a production system?",
        "Write a FAQ answer explaining what an access token is.",
        "We announced the {tech} at {p} in a media release last week. Write a social media post about it.",
        "How do I run a good negotiation workshop with my team?",
        "In general, what makes a customer contract risky for a supplier?",
        "Explain how a generator decides what to bid, in textbook terms.",
        "Which tools help with project scheduling for a {tech}?",
        "Set a placeholder like YOUR_API_KEY_HERE in this config example and explain it.",
        "Explain what 'long' and 'short' mean in energy trading.",
        "How does a generator decide when to rebid, in general?",
        "Summarise the publicly released market notice about {reg} {per}.",
        "I am learning about {mech}. Can you set a practice question with an answer?",
        "What is the usual relationship between gas prices and electricity prices in {reg}?",
    ],
}

CREDENTIALS = {
    "train": [
        "My key is {s}, why does the call fail?",
        "Here is the config: {s} can you tidy it up?",
        "Why can't I connect with {s} ?",
        "I'll paste the credential: {s} and you tell me what access it gives.",
        "Debug this for me, I set {s} in the environment file.",
        "Is it OK to commit this? {s}",
    ],
    "eval": [
        "Please check my setup. {s}",
        "The service keeps rejecting {s}. What is wrong?",
        "Format this for a README: {s}",
        "Quick question, does {s} look valid to you?",
        "Rotate this for me: {s}",
    ],
}

CUSTOMER = {
    "train": [
        "Summarise our negotiating position with {w} over {t}, and what we could give up.",
        "{w} wants {t} changed. Draft a counter-offer.",
        "Help me prepare for tomorrow's call with {w}: they are pushing back on {t}.",
        "{n} rejected our offer of ${m}/MWh. What concessions should we offer?",
        "Write an email to {n} accepting {t} but asking for better terms.",
        "List our weakest points in the negotiation with {w} about {t}.",
    ],
    "eval": [
        "We are haggling with {w} about {t}. How far can we go?",
        "Outline a fallback plan if {n} walks away from {t}.",
        "What should we trade to get {w} to agree to {t}?",
        "Our deal with {n} is stuck on {t}. Suggest a compromise to put to them.",
        "Draft talking points for the renewal with {w}; the open items are {t}.",
    ],
}

PROJECT = {
    "train": [
        "Draft the cover note for the board: we have taken an option on land at {p} for a {mw} MW {tech}, and it stays confidential until {when}.",
        "Prepare talking points for the landowner meeting about our undisclosed {tech} near {p}; nothing is public yet.",
        "Our {tech} at {p} ({mw} MW) is still under wraps. Write a Q&A for the staff who will be briefed {when}.",
        "Write the investment case for buying the {tech} site at {p}. The deal has not been disclosed.",
        "Summarise the permitting timeline for our not-yet-public {mw} MW build at {p}.",
    ],
    "eval": [
        "Keep this internal: we are in talks to acquire a {mw} MW {tech} in {p}. What diligence do we need?",
        "Outline what we tell the neighbours at {p} about the {tech} we are planning but have not revealed.",
        "Our land deal at {p} for a {mw} MW {tech} signs {when}; list the approvals still needed.",
        "Draft an internal risk summary for the secret {tech} proposal at {p}.",
    ],
}

MARKET = {
    "train": [
        "Heads up for the desk: {u} stays offline for maintenance {when} and nobody has been told. How should that change our offers in {reg}?",
        "I need a pitch for treasury: we hold {mw} MW of caps struck at ${m}, and we expect {reg} prices to blow out {when}.",
        "List the risks of our plan to park {mw} MW at {u} until prices pass ${m}/MWh.",
        "Our own modelling, not shared outside the company, puts {reg} prices {when} at ${m}/MWh. Turn that into a hedge ratio.",
        "Tell me whether offering {u} at ${m}/MWh in the early evening intervals would move the {reg} clearing price.",
        "We are about to buy {mw} MW of swaps in {reg} before the news breaks {when}. Is the timing sensible?",
        "Make a slide for the risk committee showing our open position of {mw} MW in {reg} and the offers we will put in {when}.",
        "Compare our planned offers ({u} at ${m}) against what competitors will probably do. Keep it confidential.",
    ],
    "eval": [
        "Do not share this: we are short {mw} MW in {reg} and the unit at {u} is going to trip {when}.",
        "Strategy question: our trading team wants to withhold capacity at {u} {when}; how would regulators see it?",
        "Using our private view that {reg} will average ${m}/MWh {when}, which contracts should we buy?",
        "Rank these offers for {u} by expected profit; the prices are our real planned submissions.",
        "We hold {mw} MW of unhedged exposure in {reg}. Suggest a hedge before the market learns about {u}.",
    ],
}

# (templates, labels). A few rows are positive for two policies, as real requests sometimes are.
POSITIVE_BLENDS = {
    "train": ["Using our secret price view of ${m}/MWh, draft the offer to {w} for {t}."],
    "eval": ["Our private forecast of ${m}/MWh should shape what we ask {n} to accept on {t}."],
}


def fill(template, r):
    return template.format(
        w=r.choice(WHO), n=r.choice(NAMES), t=r.choice(TERMS), p=r.choice(PLACES), mw=mw(r), when=when(r),
        tech=r.choice(TECH), m=money(r), s=secret(r), topic=r.choice(TOPICS),
        u=r.choice(UNITS), reg=r.choice(REGIONS), per=r.choice(PERIODS), mech=r.choice(MECHANICS),
    )


def build(split, counts, r, policy_ids):
    rows = {}

    def add(text, labels):
        expected = {pid: pid in labels for pid in policy_ids}
        rows.setdefault(text, expected)

    plan = [
        (SAFE, set(), counts["safe"]), (HARD_NEGATIVE, set(), counts["hard_negative"]),
        (CREDENTIALS, {"credentials"}, counts["credentials"]), (CUSTOMER, {"customer-confidential"}, counts["customer"]),
        (PROJECT, {"unannounced-projects"}, counts["project"]), (MARKET, {"market-sensitive"}, counts["market"]),
        (POSITIVE_BLENDS, {"customer-confidential", "market-sensitive"}, counts["blend"]),
    ]
    for pool, labels, n in plan:
        templates, tries = pool[split], 0
        target = len(rows) + n
        while len(rows) < target and tries < n * 50:
            add(fill(r.choice(templates), r), labels)
            tries += 1
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=int, default=800, help="approximate number of training rows (default 800)")
    ap.add_argument("--eval", type=int, default=160, help="approximate number of held-out rows (default 160)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    args = ap.parse_args()

    with open(os.path.join(ROOT, "policies.toml"), "rb") as f:
        policies = tomllib.load(f)["policies"]
    ids = [p["id"] for p in policies]
    questions = {p["id"]: scoring.question(p["criterion"]) for p in policies}
    with open(os.path.join(ROOT, "policy_cases.toml"), "rb") as f:
        test_texts = {c["text"] for c in tomllib.load(f)["cases"]}

    os.makedirs(args.out, exist_ok=True)
    for split, total in (("train", args.train), ("eval", args.eval)):
        r = random.Random(args.seed + (0 if split == "train" else 1))
        share = {"safe": .26, "hard_negative": .22, "credentials": .10, "customer": .12, "project": .10,
                 "market": .16, "blend": .04}
        counts = {k: max(1, round(total * v)) for k, v in share.items()}
        rows = build(split, counts, r, ids)
        rows = {t: e for t, e in rows.items() if t not in test_texts}  # never train or tune on the test set
        path = os.path.join(args.out, f"{split}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for text, expected in rows.items():
                f.write(json.dumps({"state": {"text": text}, "questions": questions, "expected": expected},
                                   ensure_ascii=False) + "\n")
        positives = {pid: sum(e[pid] for e in rows.values()) for pid in ids}
        print(f"{path}: {len(rows)} rows, positives per policy: {positives}")


if __name__ == "__main__":
    main()
