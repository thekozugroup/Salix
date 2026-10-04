# Validation And Reporting

Measure only what was actually run. A closer feature score is a useful signal,
not proof that the draft sounds like its author or preserves its facts.

## Read The Results

`analyze --json` returns features for cleaned prose. Cleaning removes code,
URLs, citations, and Markdown syntax for scoring; it does not authorize removing
them from the raw output. Sentence counts and word counts are algorithmic
counts, not a guarantee of agreement with a word processor.

`compare --json` returns:

- `profile`, `profile_home`, `scope`: the named voice and resolved store actually
  used, including any auto same-name global fallback.
- `total_distance`: a nonnegative weighted feature distance. Lower is closer;
  it is not bounded to 0-1 and is not a similarity/confidence percentage.
- `top_gaps`: up to ten scalar deviations, ranked by `abs_z`. `z_distance` is
  signed; `direction` says whether to raise or lower the target feature.
  `edit_hint` is a suggestion, not a safe-edit guarantee.
- `category_summary`: category averages, weights, and weighted contributions.
- `ngram_gaps`: distribution distances and divergent items. Their units differ
  from scalar z-like gaps; do not equate all scores or turn them into advice
  to copy content vocabulary.
- `all_scalar_gaps`: the full scalar feature report. `cohens_d`/`effect_size`
  labels are heuristic single-target interpretations, not significance tests.

The score combines scalar deviations, distribution distances, and a
most-frequent-word measure. It is not purely a statistical z-score. Function
words reduce topic dependence, but character fragments and other features can
still reflect content. Avoid "topic-blind", "author identified", or "validated
voice match" as unconditional claims.

Keep the profile, store, CLI version, and optional analysis backend fixed across
comparisons. Verify status and comparison profile/store metadata: auto can fall
back to a same-named global profile even when plain status selects project.
If an older comparison has no provenance fields, rerun with explicit `--home` and matching
`status --json --home`; do not infer the store from an earlier auto status.
`formality_source` can be `suffix_proxy` or `spacy`; optional spaCy
and Pyphen availability can change measurements. Record backend changes and do
not attribute them to rewriting. Tone and readability features are estimates,
not semantic truth or a human quality score.

## Rewrite Quality Gate

Do not call a rewrite ready until the raw source/final review passes:

- Facts, names, numbers with their units/associations, dates, negation, and
  qualifications retain their meaning.
- Quotes, code, URLs, and citations are unchanged.
- Required headings, section order, formatting, and audience/register survive.
- Edits read naturally; no filler or unsupported claims were added for metrics.
- Final analysis and comparison refer to the exact output being delivered.

If a check fails, correct it or retain an earlier safe candidate. Report any
unresolved check. Metric improvements cannot compensate for factual damage.

Useful before/after fields, when requested:

| Field | Meaning | Reporting |
| --- | --- | --- |
| `total_distance` | Closeness of measured features | Baseline and fresh final comparison |
| `sentence_count` | Count in cleaned prose | Original and final analysis |
| `mean_sent_len` | Mean words per sentence | Original, final, signed delta |
| `hedging_rate` | Estimated hedges per 1,000 words | Original, final, signed delta |
| `formality_f_score` | Estimated formality | Original, final, backend/source |

For a relative distance reduction, calculate
`100 * (before - after) / before` only when `before > 0`. Label it "distance
reduction", never "voice accuracy" or "style match". If the baseline is zero,
report absolute values without a percentage. Round displayed values without
implying precision beyond CLI output. Negative reduction means worsening.

## Evidence Beyond One Rewrite

Run only the relevant evaluation; never present stale example results as a
fresh validation. These commands use the same absolute CLI convention.

```bash
python3 "$SALIX_CLI" validate --authors 5 --docs-per-author 6 --seed 0
python3 "$SALIX_CLI" validate --corpus-dir "$CORPUS_DIR"
python3 "$SALIX_CLI" validate --cross-domain "$CORPUS_DIR"
python3 "$SALIX_CLI" baseline --corpus-dir "$CORPUS_DIR"
```

Default validation uses generated authors designed around the measured
features. It checks implementation consistency; it is circular evidence for
real authorship or rewrite quality. Simulation is also mechanics evidence only.

Real-corpus attribution expects at least two author folders, each with at least
three `.txt`/`.md` documents. It holds out each author's documents in turn.
Report actual authors, held-out count, correct count, accuracy, any reported
interval, corpus provenance, and exclusions. Even a "real-corpus" code path
can be fed synthetic files; label the actual data honestly. In
`validate --corpus-dir`, the additional topic-transfer and stability sections are still
synthetic; do not describe the entire report as real-corpus evidence.

Cross-domain evaluation needs at least four files per author and splits each
author's sorted filenames in half. Check those halves really represent intended
domains before claiming topic/genre transfer. Baseline comparison must use the
same corpus and account for differing evaluation splits. Neither attribution
nor domain separation proves assistant rewrite quality or factual preservation.

For performance, report only fresh timings with command, input size, environment,
backend, and repeated-run method. Do not claim latency, speedups, scalability,
accuracy, or full convergence from smoke tests or pre-existing charts.

## Completion Record

Keep the user-facing report short: outcome; file/profile/store; measured
before/after distance; host passes and stopping reason; checks performed; and
limitations or next action. If no profile exists or tooling fails, distinguish
"not measured" from "no improvement". For an analysis-only task, report
observations and no edits. For setup, report accepted/skipped samples and
profile availability, not rewrite success.
