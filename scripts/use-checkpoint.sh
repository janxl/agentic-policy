#!/usr/bin/env bash
# Load a fine-tuned decision-model checkpoint into the cluster and switch the gate to it (or back to stock).
#   scripts/use-checkpoint.sh finetune/out/tuned     copy the folder into the laya pod's volume and use it
#   scripts/use-checkpoint.sh --stock                go back to the stock model
# `make use-tuned` and `make use-stock` call this. The choice is remembered in .laya-checkpoint, so `make up`
# keeps it (and `make clean` forgets it when it deletes the volume that holds the files).
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 1
set -euo pipefail
MARK="$ROOT/.laya-checkpoint"

if [ "${1:-}" = "--stock" ]; then
  rm -f "$MARK"
  k set env deploy/laya LAYA_CHECKPOINT=
  k rollout status deploy/laya --timeout=600s
  echo "Using the stock decision model."
  exit 0
fi

dir="${1:-finetune/out/tuned}"
case "$dir" in /*) ;; *) dir="$ROOT/$dir" ;; esac
for f in model.safetensors rl_agent_config.json; do
  [ -f "$dir/$f" ] || { echo "$dir is not a checkpoint folder (no $f). Train one first: see docs/finetune/fine-tuning.md" >&2; exit 1; }
done
name="$(basename "$dir")"
remote="/cache/$name"

echo "Copying $dir into the laya pod ($remote); about 0.8 GB, without the duplicate checkpoint_latest..."
k exec deploy/laya -- sh -c "rm -rf '$remote' && mkdir -p '$remote'"
tar cf - -C "$dir" --exclude=checkpoint_latest . | k exec -i deploy/laya -- tar xf - -C "$remote"
size_local="$(stat -c %s "$dir/model.safetensors")"
size_pod="$(k exec deploy/laya -- stat -c %s "$remote/model.safetensors")"
[ "$size_local" = "$size_pod" ] || { echo "The copy is incomplete ($size_pod of $size_local bytes). Run it again." >&2; exit 1; }

echo "$remote" > "$MARK"
k set env deploy/laya LAYA_CHECKPOINT="$remote"
k rollout status deploy/laya --timeout=600s
echo "The pod says: $(k logs deploy/laya --tail=20 | grep 'model ready' | tail -1 | cut -c1-200)"
echo "Using $remote. Check it: make test-policy"
