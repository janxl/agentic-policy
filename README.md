# agentic-policy

A policy gate for LLM requests, running on Kubernetes on your own machine. Before a request goes to a
public LLM (Claude), a small decision model checks it against a list of data policies. If a policy
applies, the request is answered by a local model instead, or blocked.

**Status:** a demo of the idea, not production software. It has no authentication, it has only been tested on
WSL2 with k3s, and the test data is invented. The models (Laya, and the local chat model run by Ollama) are
downloaded when you install, and their own licences apply.

**New here?** [How it works](HOW_IT_WORKS.md) explains how the pieces fit together, and
[The policy gate](docs/architecture/policy-gate.md) and [the decision model, policies and tests](docs/architecture/decision-model.md)
describe the policies and the results.

## 1. Install

**Requirements:** Docker, `kubectl`, `make`, `curl`, Python 3.11+, and a Kubernetes cluster. About
8 GB of free memory (local model and decision model). It runs on the CPU, so no GPU is needed (or
used). Linux and macOS work directly; on Windows use WSL2.

> **Note:** only tested on WSL2 with k3s. The other clusters below are supported by the scripts but
> have not been verified yet.

**Get a cluster** (skip if you already have one that `kubectl` can reach):

- **Docker Desktop:** enable Kubernetes in its settings.
- **kind / minikube / k3d:** `kind create cluster`, `minikube start` or `k3d cluster create`.
- **k3s on Linux:** `curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644`, then
  `mkdir -p ~/.kube && cp /etc/rancher/k3s/k3s.yaml ~/.kube/config`.
- **Windows (WSL2):** follow [Windows (WSL2) setup](docs/setup/wsl2.md) (a one-time WSL setting, and Docker
  reachable from WSL).
- **A remote cluster:** point `kubectl` at it and use `REGISTRY=ghcr.io/you` in the `make up` step below.

**Deploy:**

```bash
make doctor                          # check this machine is ready
cp secret.example.yaml secret.yaml   # add your Anthropic API key (without it, everything uses the local model)
make up                              # build the images and deploy everything (the decision model downloads ~0.8 GB on first start)
make models                          # download the local model (~2.5 GB)
```

Images are loaded into the cluster automatically (the right way for k3s, kind, k3d, minikube and
Docker Desktop is detected). `make help` lists every target.

## 2. Test

```bash
make open
```

Open **http://localhost:8080** (leave `make open` running) and try:

- `Explain what a capacity market is in two sentences.`: no policy applies, so Claude answers.
- `Draft a note on the renewal terms for Acme Renewables.`: a policy applies, so the local model
  answers, and the conversation stays local.
- `Why does my key sk-ant-api03-AbCdEf1234567890xyz fail?`: blocked, and never sent anywhere. (The key is made
  up.)

Each reply shows which route it took and why. **New chat** starts a fresh conversation.

Automated checks: `make test-policy` (the gate on synthetic requests) and
`make test-persistence`. To train the decision model on your own policies, see
[Fine-tuning](docs/finetune/fine-tuning.md).

## 3. Clean up

```bash
make clean                  # delete everything deployed (asks first)
```

Options, which can be combined:

```bash
make clean DRY_RUN=1        # only show what would be deleted
make clean KEEP_MODELS=1    # keep the downloaded models
make clean IMAGES=1         # also delete the built images
make clean LOCAL=1          # also delete the remembered image tag (.build-tag)
make clean YES=1            # no confirmation prompt
```

Settings and what they do: [Configuration](docs/setup/deployment.md#configuration).
