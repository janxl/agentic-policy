[← How it works](../../HOW_IT_WORKS.md) · Setup

# Model choice

The agent can answer with two models, and the [policy gate](../architecture/policy-gate.md) picks one per request.

| | Where it runs | Default use |
|---|---|---|
| **Public model** | Claude through the API (`claude-sonnet-5-5`) | Requests no policy applies to |
| **Local model** | Ollama, on this machine (`qwen3:4b-instruct`) | Requests a policy applies to |

## Choosing the model

The agent talks to both models through one API shape (Ollama offers the same shape as Claude), so the
code ([The agent](../architecture/agent.md)) is identical for both. The agent holds two clients, `public` (Claude)
and `local` (Ollama), and picks one **per request**:

1. If the [policy gate](../architecture/policy-gate.md) says a policy applies, the request goes to `local`
   (or is blocked). The conversation then stays local.
2. Otherwise it goes to `DEFAULT_ROUTE`, which is `public` unless you change it.
3. With no `ANTHROPIC_API_KEY`, everything goes to `local`.

```bash
make use-local     # default route = local model (the gate still runs)
make use-claude    # default route = Claude; policies still divert sensitive requests
```

Both set `DEFAULT_ROUTE` on the agent. Claude needs an API key in `secret.yaml`; the model names are
`PUBLIC_MODEL` and `LOCAL_MODEL` in `k8s/agent.yaml`.

## Which to use

| | Claude | Local model |
|---|---|---|
| **Answer quality** | Strong | Noticeably weaker |
| **Speed** | Seconds | Slow on a CPU: expect several seconds to tens of seconds per answer |
| **Cost** | Pay per use | Free once downloaded |
| **Privacy** | Questions go to the API | Everything stays on your machine |
| **Needs** | An API key | About 6 GB of free memory and a 2.5 GB download |

Claude is the better choice for results. The local model is for trying the system with no account, no
cost and no data leaving the machine.

## The local model

The default is `qwen3:4b-instruct`: small enough for a laptop, and good enough to answer simple questions. It is an
*instruct* model, which answers directly. A model that "reasons" first
spends most of its output on long hidden thinking, which is slow on a CPU and uses up the limited
context window.

**CPU only.** The deployment does not request a GPU, so the local model runs on
the CPU. That is why its answers take seconds to tens of seconds. Ollama can use a GPU if your
cluster exposes one to the pod, but that needs cluster setup and an edit to `k8s/ollama.yaml`, and it
is not covered or tested here.

Settings in `k8s/ollama.yaml`:

- `OLLAMA_CONTEXT_LENGTH` (8192): how much text the model can read at once.
- `OLLAMA_KEEP_ALIVE` (30 minutes): how long it stays in memory after use. The first answer after that
  is slower, while the model reloads.

To try a different model:

```bash
LOCAL_MODEL=<name> make models     # download it
```

then set `LOCAL_MODEL` to the same name in `k8s/agent.yaml` and run `make up`.

---

← Previous: [Deployment](deployment.md) · Next: [Windows (WSL2) setup](wsl2.md)
