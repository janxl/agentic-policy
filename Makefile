# Thin wrapper over scripts/. Run `make` (or `make help`) for the list.
# Needs: bash, make, python3, curl, docker, and a Kubernetes cluster that kubectl can reach.
SHELL := /bin/bash

LOCAL_MODEL ?= qwen3:4b-instruct

# Cluster / image delivery (see scripts/load-images.sh):
#   CLUSTER=k3s|kind|k3d|minikube|shared-docker   (default: detected from the kubectl context)
#   REGISTRY=ghcr.io/you                          (push images instead; the cluster pulls them)
export CLUSTER REGISTRY KEEP_MODELS IMAGES LOCAL YES DRY_RUN   # CLUSTER/REGISTRY: image delivery; the rest: `make clean`

K := bash scripts/k.sh
APPS := agent gateway laya

.DEFAULT_GOAL := help
.PHONY: help doctor up config models use-local use-claude use-tuned use-stock \
        open logs status test-policy test-persistence clean

help:  ## show this list
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  make %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

doctor:  ## check this machine is ready (tools, cluster, storage, memory) and say how to fix gaps
	@bash scripts/doctor.sh

# ---- first-time setup: make doctor; make up; make models; make open

up:  ## build and deploy everything (first install, and again after any code change)
	bash scripts/build.sh
	bash scripts/apply.sh k8s/namespace.yaml
	bash scripts/apply-config.sh
	@if [ -f secret.yaml ]; then bash scripts/apply.sh secret.yaml; \
	  else echo "note: no secret.yaml, so no Anthropic key: every request will use the local model (see README)"; fi
	bash scripts/apply.sh k8s/ollama.yaml k8s/laya.yaml k8s/agent.yaml k8s/gateway.yaml
	@if [ -f .laya-checkpoint ]; then $(K) set env deploy/laya LAYA_CHECKPOINT=$$(cat .laya-checkpoint); fi  # keep a tuned model chosen with `make use-tuned`
	$(K) rollout restart $(addprefix deploy/,$(APPS))
	@for d in ollama $(APPS); do $(K) rollout status deploy/$$d --timeout=1800s || exit 1; done
	@echo; echo "Up. First time? Next: make models; make open  (the first start of laya downloads its model)"

config:  ## after editing policies.toml: publish it and restart the agent
	bash scripts/apply-config.sh
	$(K) rollout restart deploy/agent
	@for d in agent; do $(K) rollout status deploy/$$d --timeout=300s || exit 1; done

# ---- models

models:  ## download the local chat model (~2.5 GB) into Ollama
	$(K) exec deploy/ollama -- ollama pull $(LOCAL_MODEL)

use-local:  ## send EVERY request to the local model by default (the policy gate still runs)
	$(K) exec deploy/ollama -- ollama run $(LOCAL_MODEL) --keepalive 30m "hi" >/dev/null
	$(K) set env deploy/agent DEFAULT_ROUTE=local

use-tuned:  ## load a fine-tuned decision model into the cluster and use it (CHECKPOINT=finetune/out/tuned)
	bash scripts/use-checkpoint.sh $(or $(CHECKPOINT),finetune/out/tuned)

use-stock:  ## go back to the stock decision model
	bash scripts/use-checkpoint.sh --stock

use-claude:  ## send requests to Claude by default; policies still divert sensitive ones to the local model
	$(K) set env deploy/agent DEFAULT_ROUTE=public

# ---- day to day

open:  ## serve the UI on http://localhost:8080 (leave running)
	bash scripts/portforward.sh

logs:  ## follow the agent logs (full LLM requests/responses unless LOG_LLM=false)
	$(K) logs -f deploy/agent

status:  ## what is running, recent warnings, log tails
	@bash scripts/status.sh

test-policy:  ## run the policy gate over synthetic requests: what rules catch, what the model adds, what slips through
	bash scripts/test-policy.sh

test-persistence:  ## chat, restart the agent mid-conversation, check the history survived
	bash scripts/test-persistence.sh

clean:  ## delete everything deployed, to start over (asks first; KEEP_MODELS=1 IMAGES=1 LOCAL=1 DRY_RUN=1)
	@bash scripts/clean.sh
