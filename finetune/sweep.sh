#!/usr/bin/env bash
# Train several variants one after another and compare them. Each is a full run.sh run, about 5 minutes on a GPU.
#
#   bash finetune/sweep.sh               the default set below
#   bash finetune/sweep.sh "name:loss:label_smoothing:epochs" ...      your own variants
#
# The stock model is evaluated by every run (it only takes seconds on a GPU). Compare afterwards with
#   python3 finetune/compare.py
set -euo pipefail
cd "$(dirname "$0")/.."

SPECS=("$@")
[ ${#SPECS[@]} -eq 0 ] && SPECS=(
  "ce-ls05:soft-ce:0.05:5"      # plain cross-entropy with a little label smoothing
  "ce-ls10:soft-ce:0.10:5"      # more smoothing
  "rl-ls05:rlcd:0.05:5"         # the default loss, with label smoothing
)

for spec in "${SPECS[@]}"; do
  IFS=: read -r name loss smoothing epochs <<<"$spec"
  echo; echo "################ variant $name: loss=$loss label smoothing=$smoothing epochs=$epochs"
  TAG="$name" LOSS="$loss" LABEL_SMOOTHING="$smoothing" EPOCHS="$epochs" bash finetune/run.sh
done

echo; python3 finetune/compare.py
