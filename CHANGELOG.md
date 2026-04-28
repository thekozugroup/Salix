# Changelog

All notable changes to Salix. Format: [Keep a Changelog](https://keepachangelog.com/).

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
