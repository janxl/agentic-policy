[← How it works](../../HOW_IT_WORKS.md)

# The policy gate

Before a request goes to a public LLM, the agent checks it against a short list of data policies
(`policies.toml`). Only the user's request is checked.

| Outcome | What happens |
|---|---|
| **allow** | No policy applies. The request goes to the default route (Claude). |
| **local** | A policy applies. The request is answered by the local model, and the conversation stays local. |
| **block** | The request is refused and is neither stored nor sent anywhere. |

## The policies

| ID | Action | Catches |
|---|---|---|
| `credentials` | block | API keys, tokens, private keys, passwords, URLs with passwords |
| `customer-confidential` | local | Named customers and their commercial terms |
| `unannounced-projects` | local | Internal projects that are not public |
| `market-sensitive` | local | Price-sensitive information not yet public |

The names on the watchlists (Acme Renewables, Project Kestrel, and so on) are made up for the demo.
Replace them with your own in `policies.toml`, then run `make config`.

## How a request is checked

1. **Rules.** Regular expressions (`patterns`) and name lists (`watchlist`). Fast, exact, and they
   cannot be talked out of a decision. If a rule already blocks, the model is skipped.
2. **Decision model.** Laya (a small encoder that runs locally, in its own
   pod) answers one yes/no question per policy (the `criterion`). A score that reaches the policy's
   `threshold` counts as a hit. This catches paraphrases the rules cannot, such as a customer described
   without being named.

The strictest outcome wins: block, then local, then allow. Long requests are checked in overlapping
windows, up to a limit.

**It fails closed.** If the decision model cannot be reached, or the request is too long to check, the
request goes to the local model (`on_engine_error = "local"`), never to Claude.

## Local conversations stay local

The agent re-sends the whole conversation on every turn. So once a request is routed local, the
conversation is marked local-only (in the SQLite history), and later turns stay local. Otherwise the
next message would carry the earlier sensitive text to Claude.

## What the user sees

Each reply carries a note saying which route it took and which policy applied. Blocked replies are
shown in red. A banner shows when a conversation is local-only. The note holds policy IDs and
scores only, never the request text.

## Logging

The agent log has one policy line per request (action, engine, policy IDs, time) with no request
text. With `LOG_LAYA=true` (the default) the agent also logs what it sends to the decision model (the
text and the questions) and what comes back (the scores). That is useful for seeing how a decision was
made, and it **does contain the request text**, so set `LOG_LAYA=false` for anything sensitive. Likewise
`LOG_LLM` logs the full requests to and responses from the chat model.

```bash
make logs
```

For the decision model itself, the full policy list and the test cases, see
[The decision model, policies and tests](decision-model.md).

## Editing the policies

`policies.toml` per policy: `id`, `title`, `action` (`local` or `block`), `criterion` (the yes/no
question for the model), `threshold`, `message`, and optional `patterns` and `watchlist`.

```bash
make config        # publish the change and restart the agent
make test-policy   # run the synthetic requests in policy_cases.toml
```

## Measuring it

`make test-policy` runs about 45 synthetic requests (safe ones, traps such as "the password is
required", paraphrases) and prints two columns: rules only, and rules plus model. The number that
matters is **misses**: unsafe requests that were let through. Zero-shot, a small model is weaker and
more over-confident than it looks, so treat its results as something to measure on your own policies.

## Limits

- Only requests sent through this agent are checked. It is not a network-level control.
- A paraphrase the model misses gets through. The rules are the safety net for credentials.
- There is no authentication in this demo.

---

← Previous: [How it works](../../HOW_IT_WORKS.md) · Next: [The decision model, policies and tests](decision-model.md)
