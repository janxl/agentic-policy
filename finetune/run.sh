#!/usr/bin/env bash
# Fine-tune the decision model on the policies, and measure it before and after.
#
#   bash finetune/run.sh                 full fine-tune (wants a GPU: see docs/finetune/fine-tuning.md)
#   MODE=freeze bash finetune/run.sh     train only the answer heads: much faster and lighter, smaller gain
#   DRY_RUN=1 bash finetune/run.sh       set up and check the data, but do not train
#
# Settings (environment): EPOCHS=5  MICRO_BATCH=8  GRAD_ACCUM=2  DEVICE=auto  TAG=tuned
#                         LOSS=rlcd|soft-ce  LABEL_SMOOTHING=0   (the last two default to laya-train's own)
#                         OUT=finetune/out/$TAG  TRAIN_ROWS=800  EVAL_ROWS=160  BASE=convaiinnovations/laya
#                         VENV=.venv-finetune
# TAG names this variant: its checkpoint goes to finetune/out/$TAG and its results to finetune/results/$TAG.json,
# so several variants can sit side by side (see sweep.sh and compare.py).
# Results: finetune/results/*.json, and the checkpoint in $OUT (copy that folder back; it is about 0.8 GB).
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${MODE:-full}"; EPOCHS="${EPOCHS:-5}"; MICRO_BATCH="${MICRO_BATCH:-8}"; GRAD_ACCUM="${GRAD_ACCUM:-2}"
DEVICE="${DEVICE:-auto}"; TAG="${TAG:-tuned}"; OUT="${OUT:-finetune/out/$TAG}"; BASE="${BASE:-convaiinnovations/laya}"
LOSS="${LOSS:-}"; LABEL_SMOOTHING="${LABEL_SMOOTHING:-}"
TRAIN_ROWS="${TRAIN_ROWS:-800}"; EVAL_ROWS="${EVAL_ROWS:-160}"; VENV="${VENV:-.venv-finetune}"

python3 -c 'import tomllib' 2>/dev/null || { echo "Python 3.11 or newer is needed (python3 -c 'import tomllib' failed)." >&2; exit 1; }

# --system-site-packages: a GPU image (an AWS Deep Learning AMI) already has a CUDA build of PyTorch; reuse it.
[ -d "$VENV" ] || python3 -m venv --system-site-packages "$VENV"
. "$VENV/bin/activate"
pip install -q --upgrade pip
pip install -q laya
python - <<'PY'
import torch
print("PyTorch", torch.__version__, "| CUDA available:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no GPU: training will run on the CPU")
PY

mkdir -p finetune/results
python finetune/make_dataset.py --train "$TRAIN_ROWS" --eval "$EVAL_ROWS"

EXTRA=""; [ "$MODE" = freeze ] && EXTRA="--freeze-encoder"
TRAIN_EXTRA="$EXTRA"
[ -n "$LOSS" ] && TRAIN_EXTRA="$TRAIN_EXTRA --loss $LOSS"
[ -n "$LABEL_SMOOTHING" ] && TRAIN_EXTRA="$TRAIN_EXTRA --label-smoothing $LABEL_SMOOTHING"
echo; echo "== dry run: checking the data"
laya-train --data finetune/data/train.jsonl --eval finetune/data/eval.jsonl --base "$BASE" --dry-run $EXTRA
[ -n "${DRY_RUN:-}" ] && { echo; echo "Dry run only: nothing trained."; exit 0; }

echo; echo "== before: the stock model"
python finetune/evaluate.py --label stock --json finetune/results/stock.json

echo; echo "== training $TAG ($MODE, $EPOCHS epochs, device $DEVICE, loss ${LOSS:-default}, label smoothing ${LABEL_SMOOTHING:-default})"
START=$(date +%s)
laya-train --data finetune/data/train.jsonl --eval finetune/data/eval.jsonl --base "$BASE" --out "$OUT" \
  --epochs "$EPOCHS" --micro-batch "$MICRO_BATCH" --grad-accum "$GRAD_ACCUM" --device "$DEVICE" $TRAIN_EXTRA
echo "training took $(( $(date +%s) - START )) seconds"

echo; echo "== after: the fine-tuned model"
python finetune/evaluate.py --checkpoint "$OUT" --label "$TAG" --json "finetune/results/$TAG.json"

echo; echo "Done. Checkpoint: $OUT   Results: finetune/results/"
