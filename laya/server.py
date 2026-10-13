"""The decision model as a small HTTP service for the policy gate (agent/policy.py).

    POST /score  {"texts": ["..."], "policies": [{"id": "...", "criterion": "..."}]}
              -> {"scores": {"<id>": probability that the criterion holds, highest over the texts}}
    GET  /healthz

Each policy becomes one yes/no ("noul") question. All questions for a text are answered in a single
forward pass (see scoring.py).
"""
import logging
import os
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from scoring import Scorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("laya")

MODEL = os.environ.get("LAYA_MODEL", "english")  # "english" (512-token window) or "multilingual" (1,024)
CHECKPOINT = os.environ.get("LAYA_CHECKPOINT", "")  # optional: a fine-tuned checkpoint folder, used instead of MODEL

scorer = Scorer(MODEL, CHECKPOINT)
ready = threading.Event()


def load() -> None:
    scorer.warm_up()
    ready.set()
    log.info("model ready: %s", CHECKPOINT or MODEL)


threading.Thread(target=load, daemon=True).start()
app = FastAPI()


class Policy(BaseModel):
    id: str
    criterion: str


class ScoreRequest(BaseModel):
    texts: list[str]
    policies: list[Policy]


@app.post("/score")
def score(req: ScoreRequest):
    return {"scores": scorer.score(req.texts, [(p.id, p.criterion) for p in req.policies])}


@app.get("/healthz")
def healthz():
    """503 until the model is loaded, so Kubernetes does not send traffic (or the gate a timeout) early."""
    return JSONResponse({"ok": ready.is_set()}, status_code=200 if ready.is_set() else 503)
