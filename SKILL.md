---
name: salix
description: Measure writing style, build author-isolated reference profiles from original documents or social posts, and guide host-model rewrites and factual draft review. Use for voice matching, source-linked social reference libraries, style comparison, or draft review against captured author benchmarks.
---

# Salix — Personal Writing Style Replicator

Salix captures an author's stylistic fingerprint from prior writing samples, then iteratively rewrites target documents until they statistically match that fingerprint. Function-word features reduce topic sensitivity; character n-grams and other features can still reflect vocabulary and topic. Treat comparisons as descriptive guidance.

## When to use

Invoke Salix when the user asks for any of:
- Building or refreshing a style benchmark from samples ("ingest my writing", "build my profile")
- Rewriting a draft to match their style ("make this sound like me", "match my voice")
- Inspecting a document's style stats ("analyze this", "show me the metrics")
- Comparing a draft against a benchmark ("how far off is this?")

If the user provides a draft *and* references their style without a benchmark file present, run the ingest flow first.

## Social posts and source-linked references

For short social posts, external-source research, metrics-only capture, author comparisons,
or draft exclusions/approval checks, read [references/social.md](references/social.md)
and use `./salix social`. Keep metadata, excerpts, researcher summaries, comments and
shared repost bodies out of author prose. Measure only attributable complete originals
(or explicitly isolated original repost captions). Profiles stay author-isolated and
show sample/word sufficiency; small corpora are useful provisional references.

The host LLM writes content. Measurements guide broad characteristics; they are not a
fine-tuned model, an engagement predictor, or a guarantee of author identity. Preserve
the user's speaker and facts. Do not treat another author's claims as facts about the
user. Publication and factual approval are distinct from stylistic similarity.

## Architecture

```
SKILL.md                  # this file — orchestration instructions
salix                     # unified CLI (the only entry point you usually need)
scripts/
  ingest.py               # samples/ → benchmarks/<name>.json
  analyze.py              # single text → stats JSON
  compare.py              # stats vs benchmark → gap report (JSON)
  visualize.py            # render benchmark/stats as ASCII tables
  simulate_loop.py        # dry-run the iterative loop with rule-based edits
lib/
  stats.py                # feature extraction
  function_words.py       # closed-class allowlist (topic filter)
  tone.py                 # tone/hedging/formality heuristics
  distance.py             # weighted z-score L1 comparison + edit hints
  io_utils.py             # text loading + cleaning
benchmarks/               # saved author profiles (JSON)
samples/                  # raw writing samples (input)
tests/                    # smoke tests + regression tests
```

All scripts are pure Python 3.9+ stdlib. No pip installs required.

The unified `./salix` CLI is the preferred entry point. Run `./salix help`
for the full subcommand reference. The underlying `scripts/*.py` remain
available for direct use.

## Profile scopes

Salix supports both personal and project-specific style profiles:

- **Global** profiles live in `~/.salix` and follow the user across projects.
- **Project** profiles live in `<project>/.salix` and keep a client, repo, or
  writing context separate.
- **Auto** scope prefers a project profile when `.salix/` exists in the current
  project tree; otherwise it falls back to the global profile store.
- `SALIX_HOME` still overrides all scope behavior for legacy or advanced use.

Useful commands:

```
./salix init --scope global
./salix init --scope project
./salix ingest --name default --scope global
./salix ingest --name client-a --scope project
./salix compare draft.md --profile default --scope auto
```

## Workflow

### 1. First run — Build the benchmark

If `benchmarks/default.json` does not exist (check with `./salix status`):

1. Tell the user: *"No style profile found. Choose global voice (`./salix init --scope global`) or project voice (`./salix init --scope project`), then drop prior writing into the shown `samples/` folder. I need at least ~3,000 words for a stable fingerprint; 10,000+ is better."*
2. After samples are in place, run:
   ```
   ./salix ingest --name default --scope auto
   ```
3. Then run `./salix benchmark --profile default` and present the table to the user as the captured fingerprint.
4. Confirm: *"Benchmark saved. Ready to rewrite documents in this style."*

If the user wants multiple personas (formal vs casual), pass `--name <persona>` to `ingest`. Profiles are then selectable via `--profile <persona>` on every other subcommand.

### 2. Analyze a target document

When the user provides a target document:
1. Save the draft to a working file (e.g. `/tmp/salix_target.md`).
2. Run `./salix analyze /tmp/salix_target.md` to show the human-readable stats table, or `./salix analyze /tmp/salix_target.md --json --pretty > /tmp/salix_target.stats.json` to capture the raw stats for later steps.

### 3. Compare against benchmark

```
./salix compare /tmp/salix_target.md --profile default --json --pretty > /tmp/salix_gap.json
./salix gap /tmp/salix_target.md --profile default       # human-readable
```

The gap report is a ranked list of feature deviations. Each top-N entry includes:
- `z_distance` — signed normalized deviation
- `direction` — "raise" or "lower" relative to the benchmark
- `suggestion` — one-line description of the gap
- `edit_hint` — a concrete instruction the host LLM can act on directly

### 4. Iterative rewrite loop

This is the core orchestration the host model performs. Each iteration is a *minor* edit pass — preserve meaning, change only what the gap report flags.

```
for iter in 1..6:
    gap = ./salix compare TARGET --profile P --json
    if gap.total_distance < 0.15:
        break
    instructions = [g.edit_hint for g in gap.top_gaps[:3] if g.edit_hint]
    target_text = host_model_edit(target_text, instructions)
    # save target_text back to disk before re-comparing
```

Use `./salix simulate TARGET --profile P --verbose` to dry-run this loop with rule-based edits (no LLM). It validates the loop mechanics — distance must decrease across iterations and the loop must halt gracefully — before you invest LLM calls.

**Constraints during edits:**
- Do not change the document's facts, structure, or section ordering.
- Do not touch quoted material, code blocks, URLs, citations, or numerical data.
- Edits must be small: tighten/expand sentences, swap discourse markers, adjust punctuation cadence, vary sentence length distribution. Never wholesale rewrite a paragraph.
- Stop when convergence reached, or when 6 iterations cap hits, or when distance stops decreasing for 2 consecutive iterations.

### 5. Final QA

After the loop:
1. Run `./salix compare FINAL --profile P --json` one final time and show the user the before/after distance.
2. Show a 5-row diff summary: *original sentence count, final sentence count, mean sentence length delta, hedging delta, formality delta.*
3. Save the final document and tell the user the path.

## Key knobs

- **Convergence threshold** — `--threshold 0.15` (tighter = closer match, may over-edit). Default 0.15.
- **Max iterations** — `--max-iter 6`. Larger = more passes; diminishing returns past 4.
- **Profile scope** — `--scope auto|global|project|install` chooses where
  benchmarks and samples live. Use `--home PATH` for a custom store.
- **Feature weights** — `lib/distance.py:FEATURE_WEIGHTS`. Punctuation and function-word distributions weighted highest; readability lowest (it correlates with the others).
- **Topic filter** — `lib/function_words.py:FUNCTION_WORDS` is the closed-class allowlist. Function-word features use this set to reduce topic sensitivity; character n-grams and other metrics can still reflect topic.

## Validation

The metric has been empirically validated against synthetic multi-author corpora. Run `./salix validate --authors 5 --docs-per-author 6` to reproduce. Typical results:
- Attribution accuracy: **100% / 5 authors**, **90% / 10 authors** (chance: 20%, 10%)
- Topic transfer: same-author distance ~0.9 vs other-author ~3.6 — fingerprint generalizes
- Leave-one-out stability: mean drift 0.33, max 0.35 — well below typical attribution distances

## Anti-patterns

- **Do not** treat a single document as a stable benchmark — the fingerprint will overfit to one piece's topic and rhythm.
- **Do not** keep iterating past distance plateau — late iterations introduce style artifacts without improving match.
- **Do not** rewrite content words to chase vocabulary stats. Salix's vocab metrics intentionally ignore content terms.
- **Do not** ship edits that change meaning. Style match is worthless if facts shift.

## Rust upgrade path

`lib/stats.py` is the hot path (>90% of runtime on large corpora). For corpora >5MB or batch processing, replace with a PyO3 Rust crate exposing the same `analyze(text: str) -> dict` function. The skill orchestration does not need to change. Until then, pure-Python is sufficient (<200ms on a 50k-word corpus).
