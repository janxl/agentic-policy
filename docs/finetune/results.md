[← How it works](../../HOW_IT_WORKS.md) · Fine-tuning

# Results

What the policy gate catches, with rules alone, with the stock decision model, and with a fine-tuned one.
For how it works see [the decision model](../architecture/decision-model.md); for how to train and load a tuned model see
[Fine-tuning](fine-tuning.md).

**The test:** 44 hand-written requests in `policy_cases.toml`, never used for training: 25 that should not
reach Claude (5 to block, 20 to answer locally) and 19 that should be answered normally. The
**stock** model is Laya zero-shot (English). The **fine-tuned** model was trained on about 670 synthetic
rows with the default settings (5 epochs).

## The gate on the 44 cases

| | Exactly right | Unsafe requests let through | Safe requests flagged |
|---|---|---|---|
| Rules only | 28 of 44 | **16 of 25** | 0 of 19 |
| Rules + stock model | 36-37 of 44 | **7 of 25** | 0-1 of 19 |
| Rules + fine-tuned model | 42 of 44 | **2 of 25** | 0 of 19 |

The two figures for the stock model are the same model on a CPU (37, no false alarm) and on a GPU (36, one
false alarm: a harmless sentence about a password scores just over the line).

By kind (cases correct):

| Kind | Cases | Rules only | Stock | Fine-tuned |
|---|---|---|---|---|
| safe, trap, market-trap | 19 | all | all | all |
| credentials | 5 | all | all | all |
| customer, project (named) | 4 | all | all | all |
| customer-paraphrased | 2 | 0 | 1 | 2 |
| project-paraphrased | 2 | 0 | 2 | 2 |
| market | 3 | 0 | 2 | 3 |
| market-holdout | 9 | 0 | 4 | 7 |

Rules catch everything they can name (credentials, watchlist names) and nothing paraphrased. The stock
model finds 9 of the 16 cases the rules miss. The fine-tuned model finds 14. What it still misses are two
market-sensitive requests: a plan to rebid wind output, and an unpublished gas-price forecast.

## The model alone, on held-out rows

On 160 generated rows with phrasings the training data does not contain (share of real breaches found, with
precision in brackets):

| Policy | Stock | Fine-tuned |
|---|---|---|
| credentials | 94% (100%) | 100% (100%) |
| customer-confidential | 20% (83%) | 68% (77%) |
| unannounced-projects | 12% (67%) | 62% (100%) |
| market-sensitive | 56% (72%) | 88% (100%) |

Fine-tuning improves recall on every policy. The cost is a few more false alarms on
customer-confidential (5 against 1), which in the gate send a harmless request to the local model.

## Training variants

Label smoothing, which stops the model from answering at exactly 0 or 1, tried on the same data:

| Variant | Gate on 44 cases | Held-out found / precision | False positives | Accuracy vs confidence |
|---|---|---|---|---|
| stock | 36/44, 7 misses, 1 false alarm | 46% / 80% | 9 | n/a |
| default (what the table above uses) | 42/44, 2 misses | 80% / 94% | 5 | 96.4% vs 100.0% |
| cross-entropy, smoothing 0.05 | 39/44, 5 misses | 86% / 87% | 13 | 96.1% vs 97.1% |
| cross-entropy, smoothing 0.10 | 42/44, 2 misses | 68% / 99% | 1 | 95.8% vs 94.8% |
| default loss, smoothing 0.05 | 42/44, 1 miss, 1 false alarm | 64% / 97% | 3 | 94.4% vs 97.3% |

(Held-out found and precision are averaged over the four policies.)

- The default model is **over-confident**: 96.4% accurate but 99.96% sure. Its probabilities are nearly 0 or
  1, so a policy's `threshold` barely changes anything.
- Smoothing 0.10 makes confidence match accuracy and gives the fewest false alarms, but it finds fewer
  breaches (68% against 80%) and its answers still cluster at about 0.05 and 0.95. Lowering the threshold
  from 0.6 to 0.2 barely helps (68% to 69% found).
- So the choice between them is recall against false alarms, which a threshold cannot tune. A gate that puts
  security first should take the higher recall: a false alarm only sends a harmless request to the local
  model, while a miss lets a breach through. The default model is the one the demo uses.

## How to read this

- It is a demonstration, not a benchmark. There are 44 cases and one training run per variant, so one
  case moves a score by about two points and differences of a case or two are noise.
- The training data is invented and templated. `finetune/check_leakage.py` confirms no test case shares more
  than about a third of its wording with a training row, and the market cases share none; real, varied
  examples would do better.
- Model accuracy here is a claim about these policies and these phrasings, not about requests in general.

---

← Previous: [Fine-tuning on an AWS GPU](aws-gpu.md)
