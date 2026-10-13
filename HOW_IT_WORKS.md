# How it works

You talk to a **chat agent**. Before anything is sent to a public LLM, a **policy gate** checks the
request against a list of data policies. Sensitive requests are answered by a local model instead, or
blocked. The agent remembers each conversation in a small database, and a simple web page lets you
chat with it.

```
 you ──▶ web page ──▶ gateway ──▶ agent ──▶ policy gate ──▶ decision model (Laya)
                                    │             │
                                    │             ├── no policy applies ──▶ Claude
                                    │             ├── policy applies    ──▶ local model (Ollama)
                                    │             └── credentials       ──▶ blocked
                                    │
                                    └──▶ conversation history  (SQLite)
```

Each part has its own page. Read them in order for the full picture, or jump to the one you care about.

## [The policy gate](docs/architecture/policy-gate.md)

The point of this repo. Rules and a small decision model check each request against the policies in
`policies.toml` before it leaves the machine: allow (Claude), local (Ollama), or block. It fails
closed, and a conversation that went local stays local.

## [The decision model, policies and tests](docs/architecture/decision-model.md)

What Laya is, the four policies and how each is checked, the 44 test cases, and the measured result:
rules alone let 16 of 25 unsafe requests through; with the model, 7; with a fine-tuned model, 2.

## [The agent](docs/architecture/agent.md)

What happens to a message: check, route, ask the chosen model, store. Claude and the local model are
called through the same API shape, so one piece of code serves both.

## [The UI](docs/architecture/ui.md)

A minimal web page and a small gateway in front of the agent. The agent only needs "a message and a
conversation id in, a reply out", so the web page is one channel among many that could be added.

## [Conversation history](docs/architecture/conversation-history.md)

Every message is stored in SQLite, so conversations survive restarts and page reloads. It also records
which conversations are local-only, so earlier sensitive text is never re-sent to Claude.

---

## Setting it up and running it

How the system is run and configured, rather than how its pieces fit together.

### [Deployment](docs/setup/deployment.md)

Everything runs as pods in one Kubernetes namespace, with volumes for the data that must survive a
restart. `make up` builds the images and deploys the lot, and it is safe to run again after a change.

### [Model choice](docs/setup/model-choice.md)

Claude and a small local model, and how the gate chooses between them per request.

### [Windows (WSL2) setup](docs/setup/wsl2.md)

Getting k3s and Docker working inside WSL2: the one-time cgroup setting (and how to undo it), systemd,
Docker, and fixes for the usual first-install problems.

## Fine-tuning the decision model

### [Fine-tuning](docs/finetune/fine-tuning.md)

Teaching Laya the policies from labelled examples: the dataset, the one-command experiment, and how to load
the result into the gate.

### [Fine-tuning on an AWS GPU](docs/finetune/aws-gpu.md)

Renting a GPU for the training run: quota, which instance and image, what to copy up (and what not to),
running it, and shutting it down.

### [Results](docs/finetune/results.md)

What the gate catches with rules alone, with the stock decision model and with a fine-tuned one, measured on
44 test requests.
