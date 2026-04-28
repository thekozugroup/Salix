# Salix

Personal writing-style replicator. Captures an author's stylistic fingerprint
from prior writing samples, then iteratively rewrites target documents until
their measured linguistic features match.

Salix is packaged as a Claude Code skill. The host model orchestrates the
edit loop; the Python scripts here do the measurement work.

## What gets measured

- **Lexical** — type-token ratio, MTLD, mean word length, long-word ratio
- **Sentence shape** — mean & stdev of sentence length, short/long ratios, comma rate
- **Punctuation** — per-1000-word rates for `, ; : — - ( " ' ! ?` and ellipsis
- **Function-word frequencies** — closed-class words tracked individually (`perhaps`, `rather`, `quite`, `indeed`, `however`, etc.)
- **Function-word n-grams** — bi/trigrams of closed-class tokens only, so the fingerprint is **topic-blind**
- **Readability** — Flesch–Kincaid grade, Gunning Fog, ARI
- **Tone** — hedging, booster, discourse-marker rates; Heylighen–Dewaele formality F-score; passive-voice proxy; sentiment polarity
- **Paragraph shape** — mean sentences/words per paragraph
- **Sentence starters** — distribution of first-word usage

The topic filter is the key trick: vocabulary statistics consider only
function words, so the same author writing about cooking and quantum
physics produces a similar fingerprint.

## Install

```bash
# Option A — symlink into the global Claude skills folder
./install.sh

# Option B — manually
ln -s "$(pwd)" ~/.claude/skills/salix
```

After installing, restart Claude Code (or reload skills) and Salix is
available as a triggered skill.

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
```

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
lib/                      # extraction, comparison, IO
benchmarks/               # saved profiles
samples/                  # raw writing inputs
tests/                    # smoke + regression tests
install.sh                # symlink helper
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
