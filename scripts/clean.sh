#!/usr/bin/env bash
# Remove what this project deployed, so you can start again from scratch with `make up`.
#
#   make clean                  everything in the cluster: the whole namespace, including its data
#                               (downloaded models, conversations)
#   make clean KEEP_MODELS=1    same, but keep the Ollama volume so the models are not downloaded again
#   make clean IMAGES=1         also delete the built images (Docker, and k3s's containerd)
#   make clean LOCAL=1          also delete .build-tag
#   make clean DRY_RUN=1        only show what would be deleted
#   make clean YES=1            do not ask for confirmation (for scripts)
# Options combine, e.g.  make clean KEEP_MODELS=1 IMAGES=1
#
# Never touched: the cluster itself, Docker, and secret.yaml.
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 1
set -uo pipefail

KEEP_MODELS="${KEEP_MODELS:-}"; IMAGES="${IMAGES:-}"; LOCAL="${LOCAL:-}"; YES="${YES:-}"; DRY_RUN="${DRY_RUN:-}"
IMAGE_PATTERN='(^|/)agentic-decision/(agent|gateway|laya):'

ctx="$($KUBECTL config current-context 2>/dev/null || echo '?')"
have_ns() { $KUBECTL get namespace "$NS" >/dev/null 2>&1; }

# ---------------------------------------------------------------- the plan

echo "Kubernetes context: $ctx"
echo
if have_ns; then
  echo "In the cluster (namespace '$NS'):"
  k get deploy,job,svc,ingress,configmap,secret,pvc --no-headers 2>/dev/null | sed 's/^/    /' | grep -v 'kube-root-ca'
  echo
  if [ -n "$KEEP_MODELS" ]; then
    echo "  -> DELETE all of it except the 'ollama-models' and 'laya-cache' volumes (the downloaded models are kept)."
  else
    echo "  -> DELETE the whole namespace, including its DATA: the downloaded models (Ollama, Laya) and"
    echo "     the conversation history (agent)."
    echo "     (To keep the models, which are the slow part to download again: KEEP_MODELS=1)"
  fi
else
  echo "Nothing to delete in the cluster: namespace '$NS' does not exist."
fi
[ -n "$IMAGES" ] && echo "  -> DELETE the built images (agentic-decision/*) from Docker, and from k3s if that is the cluster."
if [ -n "$LOCAL" ]; then
  echo "  -> DELETE .build-tag."
fi
echo
echo "Kept: the cluster, Docker and secret.yaml."

if [ -n "$DRY_RUN" ]; then echo; echo "Dry run: nothing deleted."; exit 0; fi

# ---------------------------------------------------------------- confirm

if [ -z "$YES" ]; then
  if [ -t 0 ]; then
    echo
    read -r -p "Type 'yes' to delete: " answer
    [ "$answer" = yes ] || { echo "Aborted: nothing deleted."; exit 1; }
  else
    echo "Not a terminal, so I cannot ask: re-run with YES=1 to confirm." >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------- delete

echo
if have_ns; then
  if [ -n "$KEEP_MODELS" ]; then
    echo "Deleting workloads, config and volumes (keeping the model volumes: ollama-models, laya-cache)..."
    k delete deployment,statefulset,job,pod,service,ingress,configmap,secret --all --wait=true --timeout=180s
    k delete pvc agent-data --ignore-not-found --wait=true --timeout=180s
  else
    echo "Deleting namespace '$NS' (can take a minute while volumes are released)..."
    rm -f "$ROOT/.laya-checkpoint"  # the volume holding the tuned model goes with the namespace
    $KUBECTL delete namespace "$NS" --wait=true --timeout=240s \
      || echo "The namespace is still terminating. Check: $KUBECTL get namespace $NS -o yaml  (stuck finalizers)." >&2
  fi
  # The storage provisioner removes a claim's volume a few seconds after the claim goes (k3s local-path),
  # or never, if the storage class retains data. Wait a little, then say which ones are left.
  leftover_volumes() {
    $KUBECTL get pv -o custom-columns=NAME:.metadata.name,CLAIM:.spec.claimRef.name,NS:.spec.claimRef.namespace --no-headers 2>/dev/null \
      | awk -v ns="$NS" -v keep="${KEEP_MODELS:+1}" '$3==ns && !(keep && ($2=="ollama-models" || $2=="laya-cache"))'
  }
  for _ in $(seq 1 30); do [ -z "$(leftover_volumes)" ] && break; sleep 2; done
  left="$(leftover_volumes)"
  if [ -n "$left" ]; then
    echo "These volumes outlived their claims (this storage class retains data); delete them with 'kubectl delete pv <name>':" >&2
    echo "$left" | sed 's/^/    /' >&2
  fi
fi

if [ -n "$IMAGES" ]; then
  echo "Deleting built images..."
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "$IMAGE_PATTERN" | while read -r img; do docker rmi "$img"; done
  cluster="$(bash "$ROOT/scripts/load-images.sh" --detect 2>/dev/null)"
  case "$cluster" in
    k3s)
      k3s_bin="$(command -v k3s || echo /usr/local/bin/k3s)"
      sudo "$k3s_bin" ctr images ls -q | grep -E "$IMAGE_PATTERN" | while read -r img; do sudo "$k3s_bin" ctr images rm "$img"; done
      ;;
    kind|k3d|minikube)
      echo "Images loaded into the $cluster node are not removed here; they go when you delete that cluster." ;;
    registry)
      echo "Images pushed to $REGISTRY are not removed (delete them in the registry if you want)." ;;
  esac
fi

if [ -n "$LOCAL" ]; then
  echo "Deleting local files..."
  rm -fv "$ROOT/.build-tag"
fi

echo
echo "Clean. To start again: make up, then make models (see README)."
