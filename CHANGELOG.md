# Changelog

All notable changes to Salix. Format: [Keep a Changelog](https://keepachangelog.com/).

## [0.9.0] — 2026-04-28

Round-4 + round-5 reviewer punch lists. Final measurement-quality polish.

### Added
- **Cohen's d + effect-size band** alongside z_distance in every gap entry
  (trivial / small / medium / large per Cohen 1988). Helps users judge
  "is this gap meaningful or just within-author noise."
- **Bootstrap 95% confidence interval** on real-corpus attribution
  accuracy via 1000 percentile resamples. Reported as `accuracy_ci_95`.
- **Cross-domain stability check** — `salix validate --cross-domain <dir>`
  splits each author's docs alphabetically into halves (A train, B test)
  and reports same-author vs other-author cross-domain mean distance.
  Detects the Stamatatos 2013 cross-genre failure mode.
- **MFW re-projection** in `compute_gaps`. Target MFW vector is now
  expanded to cover every word in the benchmark's MFW vocabulary
  (zero-filling absent terms), so cross-corpus Burrows Delta isn't
  understated by silently dropped keys.
- **`_pos_sigma` persistence** — `aggregate()` stores per-POS-n-gram
  within-author sigma alongside `_mfw_sigma`.
- **Federalist Papers splitter** — `scripts/split_federalist.py` parses
  Project Gutenberg id 1404 into per-author subdirs (hamilton, madison,
  jay, disputed). `validation/SETUP_REAL_CORPUS.md` documents the full
  setup path for Federalist + PAN-13 + Reuters_50_50.
- **`stamatatos_baseline.py --json`** — machine-readable output for CI
  side-by-side comparison against Salix's full-feature distance.
- **`pyphen` UserWarning** when missing — nudges users toward
  hyphenation-dictionary syllable accuracy on Latinate prose.

### Changed
- **CHANGELOG ordering** — newest release on top per Keep-a-Changelog.
- **Sigma floor lowered from 25% → 5% of EXPECTED_SIGMA prior** with
  Argamon 2008 citation; documented as uncertainty admission rather
  than a fabricated prior.
- **k-fold leave-one-out** is now the default protocol in
  `attribution_check_real`; `kfold=False` preserves single-holdout.
- **`cmd_status`** broadens unreadable-benchmark exception list to
  `(SystemExit, OSError, ValueError, KeyError)` with type name in the
  output.
- **`_get_spacy_nlp`** moves the `import spacy` outside the lock so
  concurrent callers don't queue on first-run import latency.
- **Tone lexicon hygiene continued** — sentiment list de-duped
  (`ugly` × 2 collapsed by frozenset).

### Tests added (now 71)
- `_pos_sigma` persistence when spaCy active.
- `cross_domain_check` end-to-end on a 2-author tree.
- `attribution_check_real` reports `accuracy_ci_95`.
- Stamatatos baseline `--json` output is parseable JSON with confusion
  list-of-pairs.
- Cohen's d / effect-size present in every top gap.
- Threading test on `_get_spacy_nlp` (16 threads, asserts one load).
- PYTHONPATH pinned in subprocess test envs.

## [0.8.0] — 2026-04-28

Round-2 + round-3 reviewer punch lists. Substantial linguistic overhaul.

### Added
- **Real Burrows' Delta**. `aggregate()` persists `_mfw_sigma` (across-document
  stddev of each MFW word's per-1k rate). `_burrows_delta()` uses these honest
  sigmas; falls back to the global-σ-of-MFW-vector with a 10% floor when
  sigmas are absent.
- **POS n-grams**. `pos_ngrams()` emits POS bi/trigrams via spaCy when
  available; integrated through `aggregate()`, `compute_gaps()` n-gram TVD.
  Argamon-Koppel feature.
- **Stamatatos (2009) baseline**. `scripts/stamatatos_baseline.py` and
  `salix baseline --corpus-dir ...` implement the canonical char-3gram +
  cosine attribution method for head-to-head comparison against Salix's
  full-feature distance on the same corpus.
- **pyphen syllable counter** when installed — Hyphenation-dictionary-based,
  far more accurate than the vowel-group heuristic on Latinate / affixed
  words. Heuristic stays as a deterministic fallback.
- **Real-corpus validation mode**. `./salix validate --corpus-dir <dir>`
  with per-author subdirectories. Synthetic mode now explicitly framed as
  a sanity check, not authorship attribution.

### Changed
- **MFW aggregation units**. Explicit per-doc per-1k tracking; corpus-level
  mean is the word-count-weighted average. No more sleight-of-hand mixing
  per-1k rates with raw-mass weights.
- **`_splice_sentence`** now matches sentence boundaries via offset walk-back
  (terminator + any whitespace), supporting paragraph-internal breaks.
  Literal-find fallback removed — collision-free by construction.
- **Char n-gram script coverage** matches the tokenizer's Unicode policy
  (any letter via `isalpha()` + apostrophe + space).
- **`load_corpus` symlink containment** uses `Path.is_relative_to()` instead
  of fragile `str.startswith` (sibling-prefix bypass fixed).
- **`cmd_status`** now uses `_load_bench` for corruption-tolerant reads;
  surfaces unreadable benchmarks instead of crashing.
- **`_get_spacy_nlp`** wraps the load attempt in a `threading.Lock` and
  defers setting `_SPACY_LOAD_ATTEMPTED` until after assignment, so
  concurrent callers cannot observe partial state.
- **Honoré's R** returns 0.0 below 50 tokens and caps `1−V1/V` at 0.05 to
  prevent divergence on hapax-heavy short inputs.
- **Tone lexicons trimmed**. Removed `kind`/`sort`/`rather` from HEDGES
  (head-noun and contrastive senses dominate); `must` from BOOSTERS
  (handled in `count_modal_hedges`); `right`/`correct` from POSITIVE
  (directional/agreement senses dominate in conversational prose).

### Tests added (now 65)
- `_splice_sentence` substring-collision avoidance.
- Stamatatos baseline attribution accuracy.
- `cmd_status` graceful handling of corrupt benchmark.
- Sibling-prefix symlink rejection (catches the `startswith` trap).
- Real-corpus validation mode dispatches end-to-end.
- POS n-grams present (empty when spaCy absent).
- spaCy lazy-load (importing `lib.stats` does not load the model).
- `MAX_FILE_BYTES` rejection.
- Malformed-JSON benchmark surfaces a clear error via the CLI.


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
