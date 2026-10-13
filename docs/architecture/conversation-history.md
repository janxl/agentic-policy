[← How it works](../../HOW_IT_WORKS.md)

# Conversation history

The agent keeps each conversation's history in SQLite, a small database that lives in a single file.

## Why the agent needs it

The LLM API is stateless ([the agent](agent.md)), so the model only "remembers" what the agent sends it.
If the agent kept nothing, every message would arrive as a first message: *"and what about Q3?"* would
mean nothing without the question before it. Something has to hold the conversation between one message
and the next.

The simplest option is to keep it in the agent's memory. That breaks in three ways:

- A restart or redeploy of the agent wipes every conversation.
- A page reload gives the user a blank chat.
- Nothing is left to look at afterwards: past conversations
  are gone.

## Why SQLite

The code is `agent/history.py` (about 100 lines, standard library only). SQLite is a full SQL database
in one file: no server to run, no credentials, and transactions that survive a crash. That suits an
agent that runs on a laptop.

One table holds the conversation, one row per message, in the exact shape the LLM API expects:

```sql
CREATE TABLE messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL,      -- which conversation
  role        TEXT NOT NULL,      -- "user" or "assistant"
  content     TEXT NOT NULL,      -- JSON: a string, or a list of content blocks
  created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Each message is stored in the shape the LLM API expects, so the conversation can be replayed exactly.
A second small table, `restricted`, records which conversations are local-only and why (below).

## How a message uses it

`chat()` in `agent/app.py` does this for every message:

1. **Load** the session's rows (`history.load`).
2. **Add** the new user message to them in memory.
3. **Ask the model** the [policy gate](policy-gate.md) chose (see [the agent](agent.md)), which appends
   the reply.
4. **Save** all the new messages in one transaction (`history.append`), only if the whole turn
   succeeded.

Saving only at the end is deliberate. If the LLM call fails or times out, nothing is written, so there
is never a user message with no answer in the history to confuse the next turn. A per-session lock also
makes sure one conversation handles one message at a time.

## What the model sees

Everything is stored, but only the most recent messages are sent. A long conversation would eventually
overflow the model's context window, which is small for a local model. `for_llm()` sends the last 24
messages (`MAX_CONTEXT_MESSAGES`).

**This matters for the policy gate.** The whole conversation is re-sent on every turn, so once a
request has been kept local, the conversation is marked local-only (the `restricted` table). Otherwise a
later turn would carry the earlier sensitive text to Claude.

## Surviving restarts and reloads

- **Restarts.** The database file sits on a persistent volume (`agent-data`, mounted at `/data`), not in
  the container, so replacing the agent pod keeps every conversation. (`make clean` deletes the volume.)
- **Reloads.** The browser keeps its session id in local storage. On load the page asks for that
  conversation (gateway `/history/<id>` to the agent) and redraws it ([the UI](ui.md)). **New chat**
  just makes a new id.

## Limits, and what else exists

This is deliberately the simplest thing that works, and it has limits:

- **Old messages just fall out.** Past the 24-message window the model forgets them. Nothing summarises
  or searches them.
- **No users.** A conversation is identified only by the id in the browser. There is no login, and no
  way to list or delete past conversations.
- **One agent replica.** SQLite allows one writer on one file, so the agent runs a single pod (the
  deployment replaces the old pod before starting the new one). Several replicas would need a shared
  database such as Postgres or Redis.
- **Plain storage.** It keeps text in order and does nothing smart with it.

"Smarter" conversation memory is its own product category, and several tools exist for it. They add
things like:

- **Summarising** older turns so a long conversation still fits in context.
- **Long-term memory** that extracts facts about a user ("prefers metric units") and recalls them in
  later conversations.
- **Retrieval** of relevant past messages by meaning, instead of just the latest ones.
- **Shared, multi-user storage** that scales past one process.

Examples include Mem0, Zep and Letta (formerly MemGPT), and the persistence layers ("checkpointers") in
agent frameworks such as LangGraph, which can use SQLite, Postgres or Redis. Some LLM providers also
offer conversation state on their own servers. This project does not use any of them: for a single-user
local agent, one table and a few functions are easier to understand and enough. If you outgrow it, the
interface is small (`load`, `append`, `for_llm`, `visible`), so swapping the storage behind it would
touch one file.

---

← Previous: [The UI](ui.md) · Next: [Deployment](../setup/deployment.md)
