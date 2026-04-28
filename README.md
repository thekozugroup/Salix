# Salix

Personal writing-style replicator. Captures an author's stylistic fingerprint
from prior writing samples, then iteratively rewrites target documents until
their measured linguistic features match.

Salix is packaged as a Claude Code skill. The host model orchestrates the
edit loop; the Python scripts here do the measurement work.

## What gets measured

**Lexical & vocabulary richness**
- Type-token ratio, MTLD, mean word length, long-word ratio
- **Yule's K**, **Honoré's R**, **Simpson's D** — length-robust diversity measures

**Sentence shape**
- Mean & stdev of sentence length
- Length quantiles p25 / p50 / p75 / p90 (Mendenhall-style distribution shape)
- Short-sentence ratio, long-sentence ratio, comma-per-sentence rate

**Punctuation** — per-1000-word rates for `, ; : — - ( " ' ! ?` and ellipsis

**Topic-blind n-gram fingerprints**
- Function-word bigrams and trigrams (top-100 each, run-based extraction)
- **Character 3-grams and 4-grams** (top-200 each, cosine distance) — the
  highest-performing authorship feature in Stamatatos (2009)
- **Burrows' Delta** over the top-150 most-frequent function words — the
  Argamon topic-blind variant

**Readability** — Flesch–Kincaid grade, Gunning Fog, ARI

**Tone & stance**
- Hedging rate (with **contextual disambiguation** — "May 2024" and "could
  you" no longer count as hedges)
- Booster rate, discourse-marker rate
- **Heylighen–Dewaele formality F-score** (uses real spaCy POS counts when
  spaCy is installed; otherwise a deterministic suffix proxy)
- Passive-voice rate
- Sentiment polarity (~110-item AFINN-aligned lexicon)

**Paragraph shape** — mean sentences/words per paragraph

**Sentence starters** — distribution of first-word usage

The topic filter is the key trick: vocabulary statistics consider only
function words, and n-grams come from FW runs only, so the same author
writing about cooking and quantum physics produces a similar fingerprint.

Each benchmark also persists a per-feature **empirical sigma** computed from
within-author variation across the input documents — distance z-scores at
compare time use *the author's own* variability rather than a fabricated
prior.

## Install

```bash
# Option A — symlink into the global Claude skills folder
./install.sh                # interactive overwrite prompt
./install.sh --force        # non-interactive (CI / dotfiles)

# Option B — manually
ln -s "$(pwd)" ~/.claude/skills/salix

# Option C — pip install as a regular package (development)
pip install -e .
```

Requires Python 3.9+. Pure stdlib at runtime — no required dependencies.
Optional: `spacy` + `en_core_web_sm` for higher-quality formality scoring.

After installing, restart Claude Code (or reload skills) and Salix is
available as a triggered skill.

`SALIX_HOME` overrides the directory used for benchmarks/ and samples/
(default: the install directory). Set it when running multiple sessions
that should not share state.

## Use directly (without Claude)

The unified CLI bundles every step. Run `./salix help` for the full reference.

```bash
# 0. See current state (profiles, samples, what to do next)
./salix status

# 1. Drop writing samples in samples/
cp ~/Documents/old_essays/*.md samples/

# 2. Build benchmark from those samples
./salix ingest --name default

# 3. Inspect the fingerprint
./salix benchmark --profile default

# 4. Analyze a draft
./salix analyze draft.md

# 5. See the gap (human-readable)
./salix gap draft.md --profile default

# 5b. Get the gap as JSON for downstream tooling
./salix compare draft.md --profile default --json --pretty > gap.json

# 6. Dry-run the rewrite loop using rule-based edits (no LLM required)
./salix simulate draft.md --profile default --verbose --out rewritten.md

# 7. Run the validation harness — empirical evidence the metric works
./salix validate --authors 5 --docs-per-author 6 --out validation/results.md
```

## Validation

`./salix validate` exercises the metric against synthetic multi-author corpora
where each pseudo-author has a distinct, controlled style profile.

> **⚠️ The synthetic harness is a sanity check, not authorship attribution.**
> The pseudo-author knobs (sentence length, comma rate, hedge rate, register,
> passive rate) overlap with Salix's own measured features, so a high
> accuracy on synthetic data demonstrates *implementation correctness*, not
> real attribution power. Reported synthetic numbers — 100% / 5 authors,
> 90% / 10 authors, 4× same-vs-other distance separation, 0.33 mean LOO
> drift — establish that the plumbing works.

For meaningful attribution evidence, run against real corpora:

```bash
mkdir -p validation/corpora
# Drop one subdirectory per author with at least 3 .txt/.md docs each:
#   validation/corpora/author_a/{doc1.txt,doc2.txt,doc3.txt,...}
#   validation/corpora/author_b/...
./salix validate --corpus-dir validation/corpora
```

Recommended public corpora:
- PAN-13 / PAN-14 closed-set authorship attribution datasets
- The Federalist Papers (Madison vs Hamilton disputed papers)
- Reuters_50_50 (50 authors × 100 articles each, journalism)

The harness holds out one document per author and reports min-distance
classification accuracy. Real-corpus mode is the headline number we'd
defend; the synthetic mode stays for CI smoke and refactor regression.

## Concurrency model

Salix is **single-writer / multi-reader** within a given `SALIX_HOME`:

- `salix ingest` writes the benchmark JSON atomically (tempfile + os.replace);
  partial-write corruption is impossible.
- `salix compare` / `analyze` / `simulate` re-read the benchmark and retry
  briefly on `JSONDecodeError` to ride out the rename window on slow
  filesystems.
- Two concurrent `ingest` runs writing the *same* profile will produce a
  last-writer-wins outcome — give them distinct `--name` values, or use
  separate `SALIX_HOME` directories.

For multi-user / shared deployments, give each user their own
`SALIX_HOME`. There is no file-locking guarantee.

The actual rewrite step in production is performed by the host LLM, which
reads each `top_gaps[].edit_hint` and applies minor edits. The skill
instructions in `SKILL.md` describe that loop. `salix simulate` exists to
validate the loop mechanics (distance decreases, loop halts) before
investing LLM calls.

## Why Python instead of Rust

The original sketch proposed Rust. It was rejected for v1 because:

1. Distribution friction — a skill folder must run on whatever platform the
   user is on. Pure Python avoids cross-compilation and binary shipping.
2. Speed isn't the bottleneck — even on a 100k-word corpus, ingest finishes
   in well under a second. The orchestration loop is dominated by LLM edit
   latency, not Python feature extraction.
3. Clean upgrade path — `lib/stats.py` exposes one function (`analyze`).
   Replace it with a PyO3 binding any time without changing the rest of the
   skill.

## Layout

```
SKILL.md                  # skill orchestration prompt
salix                     # unified CLI (preferred entry point)
scripts/                  # individual CLI entry points
  ingest.py               # samples/ → benchmark
  analyze.py              # text → stats JSON
  compare.py              # stats vs benchmark → gap
  visualize.py            # render JSON as ASCII tables
  simulate_loop.py        # rule-based dry-run of the rewrite loop
  validate.py             # empirical attribution / topic / stability checks
lib/                      # extraction, comparison, IO
  stats.py                # feature extraction (incl. char-ngrams, MFW, quantiles)
  distance.py             # weighted z-score + cosine + Burrows Delta + edit hints
  function_words.py       # closed-class allowlist
  tone.py                 # hedge/booster/discourse/sentiment lexicons
  io_utils.py             # encoding-safe loading, clean_text
benchmarks/               # saved profiles (.json)
samples/                  # raw writing inputs (.txt / .md)
tests/                    # 56 unit + integration + property tests
examples/                 # dogfood example benchmark
validation/               # empirical validation reports
.github/workflows/ci.yml  # CI matrix
pyproject.toml            # packaging + ruff + mypy config
install.sh                # symlink helper (with --force)
CHANGELOG.md              # version history
```

## Tests

```bash
python3 -m unittest discover tests/
```

21 tests cover tokenization, segmentation (including lowercase prose,
decimals, abbreviations), lexical metrics, formality contrast, aggregation,
distance properties, edit-hint coverage, CLI dispatch, and the
monotonic-distance invariant of the rewrite loop.
