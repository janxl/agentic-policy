[← How it works](../../HOW_IT_WORKS.md)

# The agent

The agent is a small web service (`agent/app.py`). It receives a user's message, runs the
[policy gate](policy-gate.md), asks the model the gate chose, and returns the reply.

## What happens to a message

1. **Check.** `policy.check()` compares the message with the policies. Nothing has left the machine yet.
2. **Block?** If a policy says block, the agent replies with the reason. The message is not stored and
   not sent to any model.
3. **Route.** `choose_route()` picks `local` (Ollama) if a policy applies or the conversation is already
   local-only, otherwise the default route (`public`, Claude).
4. **Ask.** `ask()` sends the conversation to that model and appends the reply.
5. **Store.** The new messages are saved in one write, only if the call succeeded
   ([Conversation history](conversation-history.md)).

## Sending a query to the LLM

An LLM API is stateless: it remembers nothing between calls. So every call carries everything the
model needs: who it is and the conversation so far.

```json
{
  "model": "claude-sonnet-5-5",
  "max_tokens": 2048,
  "system": "You are a helpful assistant.",
  "messages": [
    {"role": "user", "content": "Explain what a capacity market is in two sentences."}
  ]
}
```

| Field | What it carries |
|---|---|
| `system` | The instructions that frame every answer (the system prompt, `SYSTEM_PROMPT`). |
| `messages` | The conversation so far, oldest first. Each message has a `role` (`user` or `assistant`) and `content`. |
| `model`, `max_tokens` | Which model to use, and the longest reply to allow. |

The response holds the answer as a list of content blocks; the agent returns the text.

## One API, two models

Ollama offers the same API shape as Claude, so the same code talks to both. The agent keeps two
clients, `public` and `local`, and the policy gate decides per request which one is used
([Model choice](../setup/model-choice.md)).

## Locking and logging

A per-session lock makes sure one conversation handles one message at a time. With `LOG_LLM=true` (the
default) every full LLM request and response is logged, which is useful for seeing exactly what was
sent to which model. The policy log line holds policy IDs only, never the request text.

---

← Previous: [The decision model, policies and tests](decision-model.md) · Next: [The UI](ui.md)
