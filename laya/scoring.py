"""Score texts against policy criteria with Laya. Shared by the HTTP server and the evaluation script.

Each policy criterion becomes one yes/no ("noul") question about the text. With `checkpoint` set (a folder
written by `laya-train`), that fine-tuned model is used instead of the stock one.
"""
import threading


def question(criterion: str) -> dict:
    """The model is asked about a named piece of state: point the criterion at it."""
    return {"type": "noul", "instructions": criterion.strip().replace("The text", "`text`", 1)}


class Scorer:
    def __init__(self, model: str = "english", checkpoint: str = ""):
        import laya  # imported here so that `question` can be used without PyTorch installed

        self.lock = threading.Lock()  # one forward pass at a time: the model is not thread-safe and the CPU is shared
        if checkpoint:
            agent = laya.load(checkpoint)
            self._predict = lambda state, questions: agent.predict(state, questions)
        else:
            router = laya.Router(default=model)
            self._predict = lambda state, questions: router.predict(state, questions, model=model)

    def warm_up(self) -> None:
        """Download (first start only) and build the model, so the first request is not slow."""
        self._predict({"text": "warm up"}, {"warm": {"type": "noul", "instructions": "Is `text` a greeting?"}})

    def score(self, texts: list[str], policies: list[tuple[str, str]]) -> dict[str, float]:
        """Probability per policy id that its criterion holds: the highest over the texts (windows)."""
        questions = {pid: question(criterion) for pid, criterion in policies}
        best = {pid: 0.0 for pid, _ in policies}
        with self.lock:
            for text in texts:
                answers = self._predict({"text": text}, questions)["answers"]
                for pid, a in answers.items():
                    best[pid] = max(best[pid], float(a["noul"]))
        return best
