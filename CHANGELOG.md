# Changelog

All notable changes to Salix. Format: [Keep a Changelog](https://keepachangelog.com/).

## [0.7.0] — 2026-04-28

Major iteration round driven by independent linguistic + engineering review.

### Added
- **Empirical within-author sigma** — `aggregate()` computes per-feature
  standard deviation across input documents and persists it in the benchmark
  under `_sigma`. Z-scores at compare time are now grounded in the author's
  own variation, with a 25% prior floor to avoid divide-by-near-zero
  explosions on consistent features.
- **Character n-grams (3 and 4)** plus cosine distance — the highest-
  performing authorship feature in Stamatatos (2009).
- **Burrows' Delta** over the topic-blind top-150 most-frequent function-
  words (Argamon variant).
- **Lexical richness, length-robust trio** — Yule's K, Honoré's R, Simpson's
  D. All three are stable across varying document lengths.
- **Sentence-length quantiles** (p25/p50/p75/p90) capture distribution shape
  rather than just mean+stdev (Mendenhall-style).
- **Modal-hedge contextual disambiguation** — "may", "might", "could",
  "would", "should" only count as hedges when followed by a verb-shaped
  token; "May 2024" and "could you" no longer inflate the hedging rate.
- **Sentiment lexicon** expanded from ~30 to ~110 items each side, AFINN-
  aligned.
- **Optional spaCy POS** for the Heylighen-Dewaele formality score — falls
  back to the suffix proxy if spaCy isn't available. `formality_source`
  field reports which path ran.
- **Validation harness** (`./salix validate`): synthetic multi-author
  attribution accuracy, topic-transfer separation, leave-one-out stability.
  Achieves 100% / 5 authors and 90% / 10 authors on synthetic corpora;
  same-author distance ≈ 0.9 vs other-author ≈ 3.6 across topics.
- **Empirical results** — `validation/results.md` shipped.
- **`SALIX_HOME` env var** for state isolation. Tests now use a tempdir
  SALIX_HOME and never write to the install's benchmarks/.
- **Atomic benchmark writes** via tempfile + os.replace.
- **Encoding-safe IO** with UTF-8 → CP1252 → Latin-1 fallback chain, BOM
  stripping, 50 MB cap. No silent U+FFFD substitution.
- **Unicode-aware tokenizer** (re.UNICODE) so accented Latin scripts decode
  into word counts.
- **Symlink-loop defense** in `load_corpus`.
- **`./salix --version`** flag.
- **`pyproject.toml`** with python_requires>=3.9, classifiers, ruff/mypy
  config; `salix-skill` is now `pip install`-able.
- **GitHub Actions CI** matrix: Python 3.9–3.13 × ubuntu/macos, ruff lint,
  empirical-validation job that uploads the report as a build artifact.
- **`install.sh --force`** non-interactive mode + Python version check.
- **Dogfood example** benchmark in `examples/example_benchmark.json`.
- **35 new tests** covering edge cases (empty, CJK, all-caps, huge inputs,
  mostly-markdown, file-of-URLs), encoding fallback, BOM, Unicode tokens,
  symlink dedup, simulator multi-seed property, validation harness.

### Changed
- **Function-word n-gram extraction** — replaced drop-windows-with-_X_ with
  run-based extraction. N-grams are counted within contiguous FW runs, not
  across content boundaries. Top-K raised to 100 to retain Burrows-relevant
  long tail.
- **Simulator splice** — `_splice_sentence` anchors edits at sentence
  boundaries; eliminates the str.replace substring-collision bug that
  occasionally rewrote the wrong span.
- **`clean_text` order** — fenced code blocks are stripped first, before
  URL/citation passes. URLs inside code blocks no longer leak. Bullet/
  numlist regex anchored at line-start so em-dash narration is preserved.
- **`datetime.utcnow()`** → timezone-aware `datetime.now(timezone.utc)`.
- Tests now isolate via SALIX_HOME and never touch the install dir.

### Fixed
- Aggregate scalar-key union across all samples (was: keys-of-first only),
  preventing silent feature drops on heterogeneous corpora.
- N-gram normalization no longer double-counts word_count weighting on
  already-normalized frequencies.

## [Unreleased]

## [0.6.0] — 2026-04-28

### Added
- Unified `salix` CLI with subcommands: `status`, `profiles`, `ingest`,
  `analyze`, `compare`, `gap`, `benchmark`, `simulate`, `help`.
- CHANGELOG (this file).
- Integration tests covering the CLI.

### Changed
- `SKILL.md` and `README.md` use the unified CLI throughout.

## [0.5.0] — 2026-04-28

### Added
- Concrete, actionable `edit_hint` field on every top gap. Hints are keyed by
  `(feature, direction)` and cover punctuation, sentence shape, lexical, tone
  (hedging, boosters, discourse markers, formality, passive voice), and
  paragraph metrics. Function-word and punctuation features fall back to
  templated hints.
- `direction` field on each gap entry (`raise` or `lower`).
- Visualizer renders the hint inline under each top-3 suggestion.

## [0.4.0] — 2026-04-28

### Added
- `scripts/simulate_loop.py`: rule-based dry-run of the iterative rewrite
  loop. Validates distance decreases monotonically, suggestions are
  actionable, and the loop halts gracefully.
- Edit-rule cycling: when the highest-priority gap has no rule that changes
  the text, fall through to the next gap. Keeps the loop unstuck.
- Broader comma-insertion candidates (coord/sub conjunctions, sentence-initial
  adverbs, position-2 fallback for long comma-less sentences).
- Regression tests for monotonic-distance and graceful-halt invariants.

## [0.3.0] — 2026-04-28

### Fixed
- Sentence segmentation handles lowercase prose. Previously the regex
  required a capital after each terminator, which caused entire lowercase
  paragraphs to register as a single sentence (mean length pinned to 95+
  words on real-world casual blogs).
- Decimal numbers (`3.14`) and additional abbreviations (`Ph.D.`, `a.m.`,
  `p.m.`) are masked before splitting.
- Ellipsis (`…`/`...`) and interrobang (`?!`/`!?`) sequences treated as
  sentence boundaries.

### Added
- Regression tests covering each segmentation case.

## [0.2.0] — 2026-04-28

### Added
- Stress-test harness across four prose styles (terse / academic / casual
  blog / technical manual). Confirmed self-distance is zero and pairwise
  distances span 2.1–4.5 across genres.

## [0.1.0] — 2026-04-28

### Added
- Initial Salix skill: feature extraction, comparison, ingestion,
  visualization, host-LLM orchestration prompt (`SKILL.md`).
- Pure Python 3.9+ stdlib implementation.
- Topic-blind fingerprinting via closed-class function-word allowlist.
- 11 unit tests covering tokenization, segmentation, lexical metrics,
  formality contrast, aggregation, distance properties, and end-to-end
  ingest.
- `install.sh` symlinks the skill folder into `~/.claude/skills/salix`.
