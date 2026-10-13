# Scripts

Most of these are called by `make`; you rarely run them directly. `make help` lists the commands.

## Called by `make`

| Script | Used by | What it does |
|---|---|---|
| `doctor.sh` | `make doctor` | Checks the machine is ready: tools (Docker first), Python version, systemd and cgroups on WSL, memory, the cluster and its default storage class. Every failure comes with the next step; WSL-specific hints appear only when WSL is detected. |
| `build.sh` | `make up` | Builds the three images (agent, gateway, laya) and hands them to `load-images.sh`. |
| `load-images.sh` | `build.sh` | Gets the built images to the cluster, whichever kind it is: k3s, kind, k3d, minikube, Docker Desktop, or a registry. `--detect` prints which one it found. |
| `apply.sh` | `make up` | Applies manifests, pointing the image names at the registry and tag in use (no change for local clusters). |
| `apply-config.sh` | `make up`, `config` | Checks `policies.toml` and `policy_cases.toml` are valid (policy actions, regexes), then publishes them as the `app-config` ConfigMap. |
| `portforward.sh` | `make open` | Serves the UI on `http://localhost:8080` (or the port you pass) and reconnects after a redeploy. |
| `status.sh` | `make status` | Shows what is running, recent warnings and the last log lines of each service. |
| `test-policy.sh` | `make test-policy` | Runs `policy_test.py` inside the agent pod. |
| `policy_test.py` | `test-policy.sh` | Runs the synthetic requests in `policy_cases.toml` through the policy gate and reports rules only vs rules plus decision model, including the unsafe requests let through. Fails only if the plain rules miss a case they should handle. |
| `test-persistence.sh` | `make test-persistence` | Chats, restarts the agent pod mid-conversation, and checks the history survived. |
| `use-checkpoint.sh` | `make use-tuned`, `use-stock` | Copies a fine-tuned checkpoint folder into the decision-model pod, checks the copy, and points the server at it (or back at the stock model). Remembers the choice in `.laya-checkpoint` so `make up` keeps it. |
| `clean.sh` | `make clean` | Deletes everything deployed (and optionally the images and the remembered image tag), after asking. Supports `DRY_RUN=1`, `KEEP_MODELS=1`, `IMAGES=1`, `LOCAL=1`, `YES=1`. |

The fine-tuning scripts are in `finetune/`, not here: see [docs/finetune/fine-tuning.md](../docs/finetune/fine-tuning.md).

## Shared helpers

| Script | What it does |
|---|---|
| `lib.sh` | Sourced by the other scripts. Finds `kubectl` and the kubeconfig, defines `k` (kubectl in the app namespace) and `in_agent` (run Python inside the agent pod), and names the images. |
| `k.sh` | `kubectl` in the app namespace using the same discovery as `lib.sh`. The Makefile calls this so it never needs to know where `kubectl` is. |

## Run by hand

| Script | What it does |
|---|---|
| `setup-wsl.sh` | Optional. Installs Docker and a single-node k3s inside WSL2 (see [docs/setup/wsl2.md](../docs/setup/wsl2.md) for the steps around it). |
