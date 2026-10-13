import json
import logging
import os
import threading
from collections import defaultdict

import anthropic
from fastapi import FastAPI
from pydantic import BaseModel

import history
import policy


SYSTEM = os.environ.get("SYSTEM_PROMPT", "").strip() or "You are a helpful assistant."


def env_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


LOG_LLM = env_flag("LOG_LLM", True)  # full LLM request/response JSON
ACCESS_LOG = env_flag("ACCESS_LOG", True)  # uvicorn's per-request "POST /chat 200" lines

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent")
logging.getLogger("uvicorn.access").disabled = not ACCESS_LOG

# Two models, chosen per request by the policy gate:
#   public  Claude through the API (needs ANTHROPIC_API_KEY); the default when no policy applies
#   local   a small model served by Ollama on this machine; used when a policy applies
PUBLIC_MODEL = os.environ.get("PUBLIC_MODEL", "claude-sonnet-5-5")
LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "qwen3:4b-instruct")
LOCAL_BASE_URL = os.environ.get("LOCAL_BASE_URL", "http://ollama:11434")
DEFAULT_ROUTE = os.environ.get("DEFAULT_ROUTE", "public")  # "public" or "local"

LLMS = {"local": (anthropic.Anthropic(base_url=LOCAL_BASE_URL, api_key="ollama"), LOCAL_MODEL)}
if os.environ.get("ANTHROPIC_API_KEY"):
    LLMS["public"] = (anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]), PUBLIC_MODEL)
else:
    log.warning("no ANTHROPIC_API_KEY: every request will use the local model (see README to add a key)")

app = FastAPI()
session_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


class ChatRequest(BaseModel):
    session_id: str
    message: str


def to_json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def plain_blocks(content) -> list[dict]:
    """SDK content blocks -> plain dicts that can be stored and replayed.

    Only text is kept: reasoning blocks are not replayed (saves tokens; unsigned ones can be
    rejected), and empty text blocks are invalid.
    """
    blocks = [{"type": "text", "text": b.text} for b in content if b.type == "text" and b.text]
    return blocks or [{"type": "text", "text": "(no response)"}]


def choose_route(decision: dict, restricted: str | None) -> tuple[str, str]:
    """(route, why) for a request the policy gate has not blocked."""
    if restricted:
        return "local", f"this conversation is local-only ({restricted})"
    if decision["action"] == "local":
        return "local", policy.explain(decision)
    if DEFAULT_ROUTE == "public" and "public" not in LLMS:
        return "local", "no public model is configured (no API key)"
    return DEFAULT_ROUTE, ""


def ask(session_id: str, messages: list, route: str) -> str:
    """One call to the chosen model with the conversation so far; appends the reply to messages."""
    client, model = LLMS[route]
    request = dict(model=model, max_tokens=2048, system=SYSTEM, messages=history.for_llm(messages))
    if LOG_LLM:
        log.info("LLM request [session=%s route=%s]\n%s", session_id, route, to_json(request))
    resp = client.messages.create(**request)
    if LOG_LLM:
        log.info("LLM response [session=%s route=%s]\n%s", session_id, route, resp.model_dump_json(indent=2))
    messages.append({"role": "assistant", "content": plain_blocks(resp.content)})
    return "".join(b.text for b in resp.content if b.type == "text")


def routing_info(route: str, why: str, decision: dict, restricted: str | None) -> dict:
    """What the UI shows about how the request was handled. Contains no request text."""
    return {
        "route": route,  # "public", "local" or "blocked"
        "model": LLMS[route][1] if route in LLMS else None,
        "why": why,
        "restricted": restricted,
        "policy": decision,
    }


@app.post("/chat")
def chat(req: ChatRequest):
    # One turn at a time per session. Work on a copy and only store it if the whole turn
    # succeeds, so a failed or timed-out call leaves no dangling user message in the history.
    with session_locks[req.session_id]:
        # The policy gate runs first, locally, before anything can leave this machine.
        decision = policy.check(req.message)
        log.info(  # policy ids only, never the request text
            "policy [session=%s] action=%s engine=%s hits=%s ms=%s",
            req.session_id, decision["action"], decision["engine"], [h["policy"] for h in decision["hits"]], decision["ms"],
        )
        restricted = history.restriction(req.session_id)
        if decision["action"] == "block":
            # Not sent to any model and not stored: it may contain a secret.
            why = policy.explain(decision)
            return {"reply": why, "routing": routing_info("blocked", why, decision, restricted)}

        route, why = choose_route(decision, restricted)
        if decision["action"] == "local" and not restricted:
            restricted = ", ".join(h["policy"] for h in decision["hits"]) or decision["note"] or "policy"
            history.restrict(req.session_id, restricted)

        stored = history.load(req.session_id)
        messages = stored + [{"role": "user", "content": req.message}]
        try:
            reply = ask(req.session_id, messages, route)
        except anthropic.NotFoundError:
            if route != "local":
                raise
            # Ollama has no such model yet. Say so in the chat; nothing is stored.
            hint = f"The local model '{LOCAL_MODEL}' is not downloaded yet. Run `make models`, then try again."
            return {"reply": hint, "routing": routing_info(route, why, decision, restricted)}
        history.append(req.session_id, messages[len(stored):])  # one atomic write for the turn
    return {"reply": reply, "routing": routing_info(route, why, decision, restricted)}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    """The conversation as a person saw it (for the UI to restore after a reload or restart)."""
    return {
        "messages": history.visible(history.load(session_id)),
        "restricted": history.restriction(session_id),  # why it is local-only, or null
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}
