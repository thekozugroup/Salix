# Salix Validation Report

## 1. Attribution accuracy

- Authors: **5**
- Documents per author (training set): **5**
- Held-out documents: **5**
- **Accuracy: 100.0%** (5/5; chance = 20.0%)

Confusion (true → predicted):
  - ✓ author 0 → predicted 0: 1
  - ✓ author 1 → predicted 1: 1
  - ✓ author 2 → predicted 2: 1
  - ✓ author 3 → predicted 3: 1
  - ✓ author 4 → predicted 4: 1

## 2. Topic transfer

Each author trained on topic A, tested on topic B. The fingerprint should rank a same-author document closer than an other-author document, even on the unseen topic.

- Mean same-author distance:  **0.904**
- Mean other-author distance: **3.599**
- Correct separations: **5/5** (100.0%)

## 3. Benchmark stability

Leave-one-out: drop each sample, re-aggregate, measure the distance between the leave-one-out and full-corpus benchmarks. Lower = more stable.

- Samples: **8**
- Mean LOO drift: **0.326**
- Max LOO drift:  **0.345**
- Per-sample drifts: [0.309, 0.3274, 0.3452, 0.3282, 0.3197, 0.3216, 0.3292, 0.3268]
