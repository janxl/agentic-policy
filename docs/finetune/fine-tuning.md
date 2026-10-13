[← How it works](../../HOW_IT_WORKS.md) · Fine-tuning

# Fine-tuning the decision model

Out of the box Laya answers the policy questions zero-shot, so it misses some paraphrased requests (see
[the decision model](../architecture/decision-model.md)). Fine-tuning teaches it from labelled examples of your own
policies. The scripts are in `finetune/`.

## 1. The data

Each training row is one request, labelled true or false for **every** policy:

```json
{"state": {"text": "..."},
 "questions": {"credentials": {"type": "noul", "instructions": "`text` contains a password, ..."}, "...": {}},
 "expected": {"credentials": false, "customer-confidential": true, "unannounced-projects": false, "market-sensitive": false}}
```

```bash
python finetune/make_dataset.py        # writes finetune/data/train.jsonl and eval.jsonl
python finetune/check_leakage.py       # how close each test case is to the training data
```

`make_dataset.py` builds about 670 training rows and 160 held-out rows from templates, with invented
companies, sites and secrets. The question wording comes from `policies.toml`, so training and serving ask
the same question. The held-out rows use different phrasings from the training rows, and
`policy_cases.toml` (written by hand) is the final test.

`check_leakage.py` flags any test case that shares much of its wording with a training row: such a case is
not a fair test. To use your own policies, edit `policies.toml`; to improve the result, replace the generated
rows with real labelled requests.

## 2. Run it

```bash
bash finetune/run.sh                 # data, check, evaluate the stock model, train, evaluate the tuned model
MODE=freeze bash finetune/run.sh     # train only the answer heads: faster and lighter, smaller gain
DRY_RUN=1 bash finetune/run.sh       # set up and check the data, train nothing
```

It needs Python 3.11 or newer and a GPU (it uses CUDA when available, or Apple's `mps`; there is no
Qualcomm or DirectML support, so on a Snapdragon laptop it falls back to a CPU, which is slow). On an NVIDIA
A10G training takes about 5 minutes. No GPU of your own? Rent one: [Fine-tuning on an AWS GPU](aws-gpu.md).

The checkpoint is written to `finetune/out/<TAG>` (about 0.8 GB, plus an equal-sized `checkpoint_latest`
copy you can delete) and the numbers to `finetune/results/<TAG>.json`. Settings are environment variables,
listed at the top of the script: `TAG` (default `tuned`), `EPOCHS`, `MICRO_BATCH`, `GRAD_ACCUM`, `LOSS`,
`LABEL_SMOOTHING`, `TRAIN_ROWS`, `EVAL_ROWS`.

To try several settings and compare them:

```bash
bash finetune/sweep.sh               # trains a few label-smoothing variants, then prints a comparison
python finetune/compare.py           # the comparison again, from the saved results
```

`evaluate.py` is what measures a checkpoint. It reports the model alone on the held-out rows (per policy,
how many breaches it finds and how many of its alarms are right) and the whole gate on `policy_cases.toml`.

## 3. Use the result

```bash
make up                                         # once, so the decision-model image supports checkpoints
make use-tuned                                  # copies finetune/out/tuned into the cluster and switches to it
make use-tuned CHECKPOINT=finetune/out/<TAG>    # or another checkpoint folder
make test-policy                                # the gate's numbers with the tuned model
make use-stock                                  # back to the stock model
```

`make use-tuned` copies the folder into the decision-model pod's volume, checks the copy is complete, and
sets `LAYA_CHECKPOINT`. It remembers the choice in `.laya-checkpoint`, so a later `make up` keeps it. The pod's
log should say `model ready: /cache/tuned`; `model 'english' ready` means an old image is still running and the
setting is being ignored.

## Notes

- **Results.** What fine-tuning buys, by kind of request and by policy, is in [Results](results.md).
- **Thresholds.** The default tuned model answers at nearly 0 or 1, so a policy's `threshold` barely matters.
  `LOSS=soft-ce LABEL_SMOOTHING=0.1` brings its confidence in line with its accuracy, at the price of finding
  fewer breaches. Choose between models on recall against false alarms.
- **Data.** The generated rows are templated, so the model learns their style. Real, varied labelled requests
  matter more than more templated ones.
- **Tied to the questions.** If you change a policy's `criterion`, retrain.
- Training is not covered by the repo's automated tests. `DRY_RUN=1` checks the data and setup.

---

← Previous: [Windows (WSL2) setup](../setup/wsl2.md) · Next: [Fine-tuning on an AWS GPU](aws-gpu.md)
