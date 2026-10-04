# Measurement And Verification

Salix computes stylistic features locally. The host assistant supplies prose and
edits. No model, inference service, or rewrite API is bundled with the runtime.

## Features

| Group | Measurements |
| --- | --- |
| Lexical | TTR, MTLD, Yule's K, Honore's R, Simpson's D, word length, long-word ratio |
| Sentence | Mean, standard deviation, short/long ratio, length quantiles, comma cadence |
| Punctuation | Per-1,000-word rates for commas, semicolons, colons, dashes, quotes, parentheses, question/exclamation marks, ellipses |
| Readability | Flesch-Kincaid grade, Gunning Fog, ARI |
| Tone | Hedging, boosters, discourse markers, sentiment lexicons, formality, passive-voice proxies |
| Paragraph | Mean sentences and words per paragraph |
| Distributions | Function-word bigrams/trigrams, sentence starters, character 3/4-grams, POS bigrams/trigrams, frequent function words |

Function-word sequences limit topical vocabulary influence. Character n-grams,
word lengths, readability, and other features still depend on topic, length, and
formatting. **The entire fingerprint is not topic-blind.** Lexicon/proxy tone
scores are not semantic judgments. Short documents and repeated samples can
produce misleadingly stable values.

Per-document features are aggregated by word count. Multi-document profiles save
empirical within-author standard deviations. Scalar gaps are normalized using
those deviations where usable, with heuristic floors/fallbacks. Category weights
combine scalar deviations and distribution distances into `total_distance`.
Distribution metrics include total variation, cosine distance, and a
function-word Burrows Delta variant. This combined score is not calibrated to
authorship probability, a percentage match, or a universal acceptance threshold.

Optional spaCy plus `en_core_web_sm` supplies POS features/formality counts.
Without it, formality uses a heuristic and POS lists are unavailable. Optional
pyphen changes syllable estimates. Compare runs with the same backend; the demo
records its backend and source hashes for reproducibility.

## Evidence Levels

- **Regression tests:** confirm specific behavior and edge cases, not all possible inputs.
- **Synthetic validation:** controlled generated authors share knobs with the metric.
  Good separation is a sanity check, not real-world attribution accuracy.
- **Metric fixture:** stored texts move toward copied benchmark text. Measured data
  and hash checks validate the chart pipeline, not recursive AI writing.
- **Real-corpus checks:** use independent author documents through `validate --corpus-dir`.
  Report corpus/splits and held-out results; do not generalize from one corpus.
- **Host rewrite evaluation:** requires actual prompts, model/settings, intermediate
  drafts, held-out benchmark samples, and independent checks of meaning and quality.
  The repository's Sherlock fixture does not provide this evidence.

## Reproduce

```bash
python3 -m unittest discover -v tests/
python3 -m ruff check lib/ scripts/ salix tests/
./salix validate --seed 0 --authors 5 --docs-per-author 6 --out validation/results.md
python3 scripts/demo_convergence.py
python3 scripts/build_skill_bundle.py --release
```

The simulator performs rule-based diagnostic edits. It can plateau and can alter
meaning; do not use it as the production rewrite engine or replace source files
with its output. Actual skill rewrites preserve the original and prioritize
meaning over score. Default host edit limits are deliberately bounded.

## Performance

Use `python3 scripts/benchmark_runtime.py --baseline-ref 65b6f59` to time a repeated local workload.
Record the command, Python/platform, corpus size, optional backend, and baseline
commit. Compare identical inputs/backends on the same machine after warm-up.
Wall-clock results are machine-dependent and do not predict host-model latency.
Metric equivalence must be tested before claiming a speed improvement.

The checked-in [timing run](../validation/runtime-performance.json) used Python
3.11.1 on macOS arm64, warmed heuristic backends, seven batches of five analyses.
Baseline `65b6f59` and current results were exactly equal on all three workloads.

| Workload | Baseline median | Updated median | Time reduction |
| --- | ---: | ---: | ---: |
| 56 words | 1.0337 ms | 0.8036 ms | 22.26% |
| 14,000 words, many paragraphs | 165.8475 ms | 106.9098 ms | 35.54% |
| 25,000 repeated words | 266.5950 ms | 182.0439 ms | 31.72% |

This measures local scoring only, not end-to-end assistant latency. Optional
real spaCy/pyphen workloads remain unbenchmarked.

## Release Checks

The test suite exercises copied/project installations, protected upgrades/removal,
extracted archives, CLI errors, JSON output, profile scope, and opt-in hook context.
Bundle files are allowlisted, ordered, and given fixed ZIP timestamps/modes.
SHA-256 hashes check byte integrity; no signing or supply-chain attestation is
implied. CI tests macOS/Linux and Python 3.9-3.13. A local test pass is not proof
that a remote CI run or release publication succeeded.
