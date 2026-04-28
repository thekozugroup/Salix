---
name: salix
description: Use when the user wants to rewrite a document in their personal writing style, ingest writing samples to build a style fingerprint, or analyze stylistic features of text. Triggers on phrases like "make this sound like me", "match my style", "rewrite in my voice", "/salix", "build my style profile", "ingest my writing", or any request to align a draft with a previously captured author benchmark. Iteratively edits a target document until its measured linguistic features converge to the saved benchmark.
---

# Salix — Personal Writing Style Replicator

Salix captures an author's stylistic fingerprint from prior writing samples, then iteratively rewrites target documents until they statistically match that fingerprint. Style is measured topic-blind: content words are filtered out so the benchmark reflects *how* the author writes, not *what* they write about.

## When to use

Invoke Salix when the user asks for any of:
- Building or refreshing a style benchmark from samples ("ingest my writing", "build my profile")
- Rewriting a draft to match their style ("make this sound like me", "match my voice")
- Inspecting a document's style stats ("analyze this", "show me the metrics")
- Comparing a draft against a benchmark ("how far off is this?")

If the user provides a draft *and* references their style without a benchmark file present, run the ingest flow first.

## Architecture

```
SKILL.md                  # this file — orchestration instructions
scripts/
  ingest.py               # samples/ → benchmarks/<name>.json
  analyze.py              # single text → stats JSON
  compare.py              # stats vs benchmark → gap report (JSON)
  visualize.py            # render benchmark/stats as ASCII tables
lib/
  stats.py                # feature extraction
  function_words.py       # closed-class allowlist (topic filter)
  tone.py                 # tone/hedging/formality heuristics
  distance.py             # weighted z-score L1 comparison
  io_utils.py             # text loading + cleaning
benchmarks/               # saved author profiles (JSON)
samples/                  # raw writing samples (input)
tests/                    # smoke tests
```

All scripts are pure Python 3.9+ stdlib. No pip installs required.

## Workflow

### 1. First run — Build the benchmark

If `benchmarks/default.json` does not exist:

1. Tell the user: *"No style profile found. Drop your prior writing into `samples/` (any mix of `.txt`, `.md`) or paste samples and I'll create files. I need at least ~3,000 words for a stable fingerprint; 10,000+ is better."*
2. After samples are in place, run:
   ```
   python3 scripts/ingest.py --samples samples/ --out benchmarks/default.json --name "default"
   ```
3. Then run `python3 scripts/visualize.py benchmarks/default.json` and present the table to the user as the captured fingerprint.
4. Confirm: *"Benchmark saved. Ready to rewrite documents in this style."*

If the user wants multiple personas (formal vs casual), pass `--name <persona>` and store under `benchmarks/<persona>.json`.

### 2. Analyze a target document

When the user provides a target document:
1. Save the draft to a working file (e.g. `/tmp/salix_target.md`).
2. Run `python3 scripts/analyze.py /tmp/salix_target.md > /tmp/salix_target.stats.json`.
3. Run `python3 scripts/visualize.py /tmp/salix_target.stats.json` and show the user.

### 3. Compare against benchmark

```
python3 scripts/compare.py \
  --target /tmp/salix_target.stats.json \
  --benchmark benchmarks/default.json \
  --out /tmp/salix_gap.json
```

`compare.py` prints a ranked gap report: each feature's z-distance from the benchmark, with direction ("too high" / "too low") and a human-readable suggestion. The top-N gaps drive the next edit pass.

### 4. Iterative rewrite loop

This is the core orchestration the host model performs. Each iteration is a *minor* edit pass — preserve meaning, change only what the gap report flags.

```
for iter in 1..6:
    gap = compare(target_stats, benchmark)
    if gap.total_distance < 0.15:
        break
    suggestions = gap.top_gaps[:3]   # focus only on top 3 per pass
    target_text = host_model_edit(target_text, suggestions)
    target_stats = analyze(target_text)
```

**Constraints during edits:**
- Do not change the document's facts, structure, or section ordering.
- Do not touch quoted material, code blocks, URLs, citations, or numerical data.
- Edits must be small: tighten/expand sentences, swap discourse markers, adjust punctuation cadence, vary sentence length distribution. Never wholesale rewrite a paragraph.
- Stop when convergence reached, or when 6 iterations cap hits, or when distance stops decreasing for 2 consecutive iterations.

### 5. Final QA

After the loop:
1. Run `compare.py` one final time and show the user the before/after distance.
2. Show a 5-row diff summary: *original sentence count, final sentence count, mean sentence length delta, hedging delta, formality delta.*
3. Save the final document and tell the user the path.

## Key knobs

- **Convergence threshold** — `--threshold 0.15` (tighter = closer match, may over-edit). Default 0.15.
- **Max iterations** — `--max-iter 6`. Larger = more passes; diminishing returns past 4.
- **Feature weights** — `lib/distance.py:FEATURE_WEIGHTS`. Punctuation and function-word distributions weighted highest; readability lowest (it correlates with the others).
- **Topic filter** — `lib/function_words.py:FUNCTION_WORDS` is the closed-class allowlist. Vocabulary statistics only consider words in this set, making the fingerprint topic-blind.

## Anti-patterns

- **Do not** ingest a single document as the benchmark — the fingerprint will overfit to one piece's topic and rhythm.
- **Do not** keep iterating past distance plateau — late iterations introduce style artifacts without improving match.
- **Do not** rewrite content words to chase vocabulary stats. Salix's vocab metrics intentionally ignore content terms.
- **Do not** ship edits that change meaning. Style match is worthless if facts shift.

## Rust upgrade path

`lib/stats.py` is the hot path (>90% of runtime on large corpora). For corpora >5MB or batch processing, replace with a PyO3 Rust crate exposing the same `analyze(text: str) -> dict` function. The skill orchestration does not need to change. Until then, pure-Python is sufficient (<200ms on a 50k-word corpus).
