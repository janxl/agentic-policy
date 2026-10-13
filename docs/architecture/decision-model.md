[← How it works](../../HOW_IT_WORKS.md)

# The decision model, the policies and the tests

The [policy gate](policy-gate.md) has two layers: exact **rules**, and a small **decision model** (Laya)
for what rules cannot see. This page covers the model, the policy file, and the test cases that show
what the model adds.

## The decision model: Laya

[Laya](https://huggingface.co/convaiinnovations/laya) is a small encoder model, not a chat model. It
does not write text. It reads a piece of text and answers fixed questions about it in one pass, each
answer a probability. That makes it fast on a CPU (about one second per request here), and its answers
are numbers that can be compared with a threshold, so the gate's decision is the same every time for
the same input.

- **One question per policy.** Each policy's `criterion` becomes a yes/no question, for example "The text
  discusses a named customer or counterparty together with contract terms, pricing or negotiation."
  Laya returns the probability that it is true.
- **Zero-shot by default.** The questions are asked with no training on this organisation's data. That is
  why it is useful straight away and also why it is imperfect (see the results below). It can be
  fine-tuned on labelled examples: see [Fine-tuning the decision model](../finetune/fine-tuning.md).
- **Its own pod.** `laya/server.py` wraps it as `POST /score` (a list of texts and policies in, one
  probability per policy out). The agent calls it over HTTP. The weights (about 0.8 GB) download on the
  first start into the `laya-cache` volume. Setting `LAYA_CHECKPOINT` loads a fine-tuned model instead
  (`make use-tuned`).
- **Window.** The English model reads about 512 tokens at a time. Longer requests are split into
  overlapping windows and the highest probability counts. The gate screens at most 12 windows of 1,200
  characters, and anything longer is routed to the local model rather than sent unchecked.
- **Language.** `LAYA_MODEL=multilingual` switches to the multilingual checkpoint (1,024-token window).

The model only *adds* protection. Rules run first, and a request a rule already blocks is never sent to
the model.

## Why a small local model, and not an LLM

The gate has to decide, for every request, whether it may go to a public LLM. A small local decision model
is a better fit for that than another LLM call:

- **Privacy.** The check has to happen before the request leaves the machine, so it cannot be done by the
  public model. A local model keeps the text on the machine, so nothing sensitive is exposed in order to
  find out whether it is sensitive.
- **Fast and cheap.** The check runs on every request. A small model answers quickly and costs nothing per
  request beyond the hardware you already run it on. An LLM call adds latency and, for a public model, a bill
  on every request.
- **Numbers, not text.** The model returns a probability for each policy question, so the decision is a
  comparison with a threshold. There is no prompt to engineer and no free text to parse, and the same
  request gives the same scores on the same machine. An LLM returns text that has to be interpreted and can
  vary from run to run.

A large LLM may understand subtle wording better. That is why the rules stay in front of the model as a
safety net, and why the gate fails closed.

**Laya is the model used in this demo.** It is small (about 0.8 GB), has an open licence (Apache-2.0) and can be
fine-tuned on your own policies ([Fine-tuning](../finetune/fine-tuning.md)). It is small enough that this demo
runs it on an ordinary CPU, at about a second per request; a local GPU would be faster and changes nothing
else. Any small model that scores yes/no questions could take its place: the gate only needs the `/score`
interface.

## The policies (`policies.toml`)

Four demo policies. The names in the watchlists are invented.

| ID | Action | Rules (exact) | Model question (`criterion`) |
|---|---|---|---|
| `credentials` | **block** | Nine regular expressions: Anthropic and other API keys, AWS keys, GitHub and Slack tokens, private keys, bearer tokens, URLs with a password, `password: ...` style assignments | "...a password, API key, access token, private key or other secret credential." |
| `customer-confidential` | local | Watchlist of three customer names | "...a named customer or counterparty together with contract terms, pricing or negotiation." |
| `unannounced-projects` | local | Watchlist of three project code names | "...an unannounced project, site, land purchase or acquisition, with its capacity, location or timeline." |
| `market-sensitive` | local | None (model only) | "...trading positions, planned bids or offers, trading strategy or non-public forecasts." |

Each policy has:

| Field | Meaning |
|---|---|
| `id`, `title` | Name, shown in the UI note and logs |
| `action` | `block` (never sent anywhere) or `local` (answered by the local model) |
| `criterion` | The yes/no question for the model |
| `threshold` | Probability at which the model's answer counts. Defaults to `[settings] threshold` (0.6); `credentials` uses 0.8 |
| `patterns` | Regular expressions. A match fires the policy, no model needed |
| `watchlist` | Names. A case-insensitive match fires the policy |
| `message` | What the user is told |

A policy fires if **either** a rule matches **or** the model's probability reaches the threshold. If
several fire, the strictest wins: block, then local, then allow.

`[settings] on_engine_error` says what to do when the model cannot be reached or the text is too long to
screen: `local` (the default) or `block`. It never sends the request on to Claude.

Rules and model have different strengths: rules are exact and cannot be argued with, so credentials and
named projects use them. The model recognises meaning, so a customer described without being named, or
a trading position, can still be caught. To use your own policies, edit the file and run `make config`.

## The test cases (`policy_cases.toml`)

44 invented requests, each with the outcome the gate **should** give (`expect`) and a `kind`:

| Kind | Count | Expected | What it checks |
|---|---|---|---|
| `safe` | 8 | allow | Ordinary questions go to Claude and are not flagged |
| `trap` | 5 | allow | Looks risky but is fine: "what is a password manager", "the password is required to log in", "project management practices", "which customers benefit from demand response" |
| `credentials` | 5 | block | API key, password assignment, private key, URL with a password, GitHub token |
| `customer` | 2 | local | A watchlist customer is named |
| `customer-paraphrased` | 2 | local | A customer negotiation described with no name |
| `project` | 2 | local | A watchlist project is named |
| `project-paraphrased` | 2 | local | An unannounced project or acquisition described with no code name |
| `market` | 3 | local | Bids, positions and internal forecasts |
| `market-holdout` | 9 | local | An independent set of market-sensitive requests in different styles, written separately from the fine-tuning templates |
| `market-trap` | 6 | allow | Sound similar but are public data or general education |

The paraphrased and market cases are the point of the test: plain rules cannot see them.

## Running it

```bash
make test-policy
```

It runs every case through the gate **twice** inside the agent pod: once with rules only (the decision
model switched off), then with the model on. It prints each case, then totals for both, and the number
that matters most: **misses**, unsafe requests that were let through to Claude. The command fails only
if the plain rules get a case wrong that they should handle. The model's result is reported, not
asserted, because it is what is being measured.

## Results

On the 44 test cases, rules alone let 16 of the 25 unsafe requests through. Adding the stock Laya model cuts
that to 7, and a fine-tuned model to 2, with no safe request flagged. The tables, by kind of request and by
policy, are in [Results](../finetune/results.md).

For the stock model a different threshold changes the trade-off: lower it and more is caught, but more safe
requests are flagged. (A fine-tuned model answers at nearly 0 or 1, so its thresholds barely matter.)
Timing: rules take effectively no time; the model adds about one second per request on a CPU.

## Making it better

- **Fine-tune the model** on labelled examples of your own policies: see [Fine-tuning the decision model](../finetune/fine-tuning.md).
- **Tune `threshold`** per policy using `make test-policy` to see the effect (this works for the stock model).
- **Sharpen the `criterion`**: it is the question the model answers, so a specific one works better.
- **Add watchlist names and patterns** for anything you can name exactly. Rules are free and certain.
- **Add test cases** for your own policies, then measure. Misses are what to watch.

---

← Previous: [The policy gate](policy-gate.md) · Next: [The agent](agent.md)
