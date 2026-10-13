[← How it works](../../HOW_IT_WORKS.md) · Setup

# Deployment

Everything runs in one Kubernetes namespace, `agentic-decision`. `make up` builds and deploys it all; the
manifests are in `k8s/`.

```
 browser ── Ingress ───▶  gateway ──▶ agent ──┬──▶ laya        (policy decision model)
 (or make open)                               ├──▶ ollama      (local LLM)
                                              └──▶ Claude API  (public LLM, outside the cluster)

 all of it in the namespace "agentic-decision"
```

## What runs

| Pod | Image | Job |
|---|---|---|
| `gateway` | built from `gateway/` | The web page and the entry point ([The UI](../architecture/ui.md)) |
| `agent` | built from `agent/` | The agent and the policy gate ([The agent](../architecture/agent.md)) |
| `ollama` | `ollama/ollama` | Runs the local model on the CPU ([Model choice](model-choice.md)) |
| `laya` | built from `laya/` | The decision model for the [policy gate](../architecture/policy-gate.md). Downloads its weights on first start |

The three images built from this repo are made by `make up` and loaded into the cluster. On k3s, kind,
k3d, minikube and Docker Desktop that is detected automatically; for a remote cluster they are pushed to
a registry (`REGISTRY=...`).

## Networking

Every pod is reached by name inside the cluster (`agent`, `ollama`, `laya`). Only the
gateway is exposed, through an Ingress. `make open` is an alternative that forwards a local port to the
gateway, and works on any cluster, with or without an ingress controller.

## Storage

Three volumes keep data across pod restarts:

| Volume | Holds | Size |
|---|---|---|
| `agent-data` | Conversation history ([Conversation history](../architecture/conversation-history.md)) | 256 Mi |
| `ollama-models` | The downloaded models (about 2.5 GB for the default model) | 8 Gi |
| `laya-cache` | The decision model's downloaded weights (about 0.8 GB), and any fine-tuned checkpoint you load (about 0.8 GB each) | 2 Gi |

They use the cluster's default storage class. The sizes are requests: some storage classes (the k3s
default among them) do not enforce them, while others allocate and bill the full amount. The models
volume is the large one; raise it if you want several models on disk, and raise `laya-cache` in
`k8s/laya.yaml` if you keep more than one fine-tuned checkpoint (k3s's default storage does not enforce the
size, other storage classes do). `make clean` deletes the volumes (or keeps the two model volumes, `ollama-models`
and `laya-cache`, with `KEEP_MODELS=1`).

## Configuration

**`policies.toml`** (the [policy gate](../architecture/policy-gate.md)) and `policy_cases.toml` (test requests) reach
the pods as the `app-config` ConfigMap. After editing, run `make config`, which publishes them and
restarts the agent.

**The Anthropic API key** comes from `secret.yaml` as a Secret. It is optional: without it only the
local model works.

**Everything else** is an environment variable in the manifests under `k8s/`. Edit the value, then run
`make up` (or just `bash scripts/apply.sh k8s/<file>.yaml` if only the setting changed). The values
shown are the defaults. For a one-off change without editing a file:
`kubectl -n agentic-decision set env deploy/agent LOG_LLM=false`.

### Agent (`k8s/agent.yaml`)

| Setting | Default | Meaning |
|---|---|---|
| `DEFAULT_ROUTE` | `public` | `public` (Claude) or `local` (Ollama). Policies can still divert to local. `make use-local` / `make use-claude` set it |
| `PUBLIC_MODEL` | `claude-sonnet-5-5` | The Claude model |
| `LOCAL_MODEL` | `qwen3:4b-instruct` | The local model in Ollama |
| `LOCAL_BASE_URL` | `http://ollama:11434` | Where the local model's API is |
| `ANTHROPIC_API_KEY` | from `secret.yaml` | Key for Claude. Without it, every request uses the local model |
| `POLICY_CONFIG` | `/config/policies.toml` | Where `policies.toml` is mounted |
| `LOG_LAYA` | `true` | Log the full request sent to the decision model and the response received |
| `LAYA_URL` | `http://laya:8000` | Where the decision model is. Empty means rules only |
| `LAYA_TIMEOUT` | `15` | Seconds to wait for the decision model. Not in the manifest; add it to change it |
| `DB_PATH` | `/data/agent.db` | Where conversation history is stored |
| `MAX_CONTEXT_MESSAGES` | `24` | How many recent messages are sent to the model (all are stored) |
| `LOG_LLM` | `true` | Log every full request to and response from the LLM |
| `ACCESS_LOG` | `true` | Log each HTTP request |
| `SYSTEM_PROMPT` | empty | System prompt. Empty means "You are a helpful assistant." |

### Gateway (`k8s/gateway.yaml`)

| Setting | Default | Meaning |
|---|---|---|
| `AGENT_URL` | `http://agent:8000` | Where the agent is |
| `AGENT_TIMEOUT` | `300` | Seconds to wait for the agent. Not in the manifest; add it to change it |
| `ACCESS_LOG` | `true` | Log each HTTP request |

### Decision model (`k8s/laya.yaml`)

| Setting | Default | Meaning |
|---|---|---|
| `LAYA_MODEL` | `english` | `english` (512-token window) or `multilingual` (1,024) |
| `LAYA_CHECKPOINT` | empty | A fine-tuned checkpoint folder inside the pod, used instead of the stock model. Set it with `make use-tuned` ([Fine-tuning](../finetune/fine-tuning.md)) |
| `HF_HOME` | `/cache` | Where the weights are cached (the `laya-cache` volume) |

The first start downloads the weights, so the pod can take a few minutes to become ready.

### Ollama (`k8s/ollama.yaml`)

| Setting | Default | Meaning |
|---|---|---|
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Context window of the local model, in tokens |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long a model stays loaded in memory after use |
| `OLLAMA_NUM_PARALLEL` | `1` | Requests served at once (more uses more memory) |

### `make` variables

| Variable | Default | Meaning |
|---|---|---|
| `LOCAL_MODEL` | `qwen3:4b-instruct` | Local model to download with `make models` |
| `CLUSTER` | detected | `k3s`, `kind`, `k3d`, `minikube` or `shared-docker`: how images reach the cluster |
| `REGISTRY` | unset | Push images to a registry instead, e.g. `ghcr.io/you` |
| `CHECKPOINT` | `finetune/out/tuned` | Fine-tuned checkpoint folder for `make use-tuned` |

## What `make up` does

1. Builds the three images and loads them into the cluster.
2. Creates the namespace, publishes the config, and applies the secret if `secret.yaml` exists.
3. Applies the manifests for Ollama, the decision model, the agent and the gateway.
4. Restarts the agent, gateway and decision model so they run the new images, and keeps a fine-tuned model chosen
   with `make use-tuned`.
5. Waits until everything is ready.

It is safe to run again, which is how you roll out a code change.

## Limits

- **One replica of each service.** The agent uses a single SQLite file, and Ollama and the decision model each own
  one volume, so they are replaced one at a time (a brief gap on update).
- **No authentication or encryption.** Anyone who can reach the gateway can use the agent. Keep it on
  your machine or behind your own access controls.
- **The Ollama image** is `:latest`, not version-pinned.

---

← Previous: [Conversation history](../architecture/conversation-history.md) · Next: [Model choice](model-choice.md)
