# Examples

## Recorded Model Experiment

[Full real outputs and exact prompt](live_comparison.md),
[51 recorded states over 50 rewrite attempts](live_convergence.json), and
[all 101 variable charts](live_convergence_charts/README.md) now provide a real
Codex measurement-feedback experiment. See [method and limits](../docs/BENCHMARK.md).
It shows partial improvement and plateaus, not full benchmark alignment or
universal writing superiority. The older copy fixture below is kept separately
for diagnostic reproducibility and is never counted as model output.

`example_benchmark.json` is a Salix benchmark generated from the project's own
documentation (README.md, SKILL.md, CHANGELOG.md). Use it to inspect what a
real benchmark file looks like, including the `_sigma` empirical-variance
section and the function-word/character n-gram lists. Some features retain
subject-matter and length effects; the whole profile is not topic-blind.

```bash
./salix benchmark --profile example   # if symlinked into benchmarks/
# or
python3 scripts/visualize.py examples/example_benchmark.json
```

It is not intended as a "default style" — it just shows the file format.

## Static Comparison Texts

These three texts are hardcoded illustrations. They were not collected from
an AI model, prompt execution, or Salix run. Their headings describe imagined
conditions, not measured product results. They cannot establish which approach
produces better writing.

Prompt:

```text
Write a short Baker Street case note about a missing railway ticket.
```

| Base prompt only (static illustration) | Prompt plus "write in the style of Sherlock Holmes" (static illustration) | Base prompt plus Salix (static illustration) |
| --- | --- | --- |
| Holmes received a note about a missing railway ticket. He checked the details, compared the times, and realized the ticket had never been stolen. The answer was hidden in the passenger's route. | In the dim light of Baker Street, Holmes turned the railway ticket between his long fingers and gave one of those thin smiles which usually meant the matter had already resolved itself in his mind. The missing object, he said, was never truly missing at all. | To Sherlock Holmes the missing railway ticket was not a trifle, but a small fact misplaced among larger ones. I have seldom seen him regard so slight a paper with such cold attention, for in his eyes the little oblong of pasteboard eclipsed the whole confusion of the case. |

The graphs retain all three examples as constant comparison lines. The
Salix-inspired example is **not** the changing copy-fixture line.

## Deterministic Metric Fixture

**This is a deterministic metric fixture and copy-based sanity check, never
proof of AI or Salix convergence.** No model is called and no recursive rewrite
loop runs. Each snapshot depends on its step number, not the preceding text
or measured gaps. The generator interpolates seed text with sentences/tokens
copied from a Sherlock Holmes excerpt. Step 50 replaces the draft with the
exact benchmark: the excerpt repeated four times.

The values are real measurements from these constructed texts. The falling
distance is caused by copying the target, not demonstrated editing ability.
Distance zero at the end is a self-comparison sanity check. The final copy no
longer answers the missing-ticket prompt. It also jumps from 152 words at step
49 to 620 words at step 50; length, repetition, and paragraph changes affect
the metrics.

The overview preserves seven graphs over steps 0-50 (51 snapshots). The complete
100-variable set is indexed in [convergence_charts/](convergence_charts/README.md).
Each graph has five lines: three static examples, the deterministic copy path,
and the repeated-excerpt benchmark. Distribution plots show distances, not raw
frequency lists. Unavailable POS metrics are labeled as such; their zero
placeholders do not show a syntactic match.

![Deterministic metric fixture and benchmark-copy sanity check](convergence_demo.svg)

Current checked-in values, using heuristic POS/formality and vowel-group
syllable counting:

| Copy step | Total distance | Benchmark distance | Fixture sentence length | Benchmark sentence length |
| --- | ---: | ---: | ---: | ---: |
| 0 | 2.0136 | 0.0000 | 5.4444 | 17.2222 |
| 10 | 1.5582 | 0.0000 | 7.8889 | 17.2222 |
| 20 | 1.3967 | 0.0000 | 10.5556 | 17.2222 |
| 30 | 1.0128 | 0.0000 | 13.1111 | 17.2222 |
| 40 | 0.7769 | 0.0000 | 15.3333 | 17.2222 |
| 50 | 0.0000 | 0.0000 | 17.2222 | 17.2222 |

| Static example | Total distance | Sentence length |
| --- | ---: | ---: |
| Base example | 1.9873 | 10.6667 |
| Style example | 1.8247 | 23.0000 |
| Salix-inspired example | 1.6811 | 24.5000 |

## Provenance And Reproduction

[convergence_demo.json](convergence_demo.json) uses schema version 2. It stores
the exact excerpt, repeated benchmark, three comparison texts, and every
snapshot, each with a SHA-256 hash of its UTF-8 text (whitespace preserved).
Benchmark values, comparison values, snapshot values, and series metadata are
stored once; chart point arrays are reconstructed rather than duplicated.

The provenance section records hashes of the generator and metric source
files, Python version, and POS/syllable backends. Reproduce the values with the
same sources and backends. Installing spaCy's English model or pyphen can
change metrics; neither is present in this checked-in run. Source hashes are
local reproducibility checks, not authenticated evidence of model execution.
The stored excerpt's attribution is
[The Adventures of Sherlock Holmes, Project Gutenberg](https://www.gutenberg.org/ebooks/1661).
The generator uses that embedded excerpt offline; it does not fetch the source.

Run from the repository root:

```bash
python3 scripts/demo_convergence.py
python3 -m unittest discover -s tests -p test_demo_evidence.py
```

Generation overwrites only its named chart outputs and index. It does not
delete arbitrary SVGs in the chart folder; obsolete files may remain unindexed.
`validation.passed` means text/hash/source and metric consistency only.
`completion.status` means all fixture snapshots were generated, not that a
rewrite succeeded. Independent tests remeasure recorded texts and reject
tampered evidence or claims of AI/Salix generation or convergence.

## Copy-Fixture Evidence Limits

This copy fixture has no recorded models, providers, inference settings, real prompt
outputs, gap-driven model edits, independent benchmark corpus, held-out texts,
or evaluations of originality, task fidelity, meaning preservation, and
writing quality. Repeated training-text copying cannot substitute for those.
This fixture supports inspecting the metrics and chart pipeline only. The
separate recorded experiment above supplies actual drafts but retains its own
single-run, corpus, semantic-quality, and host-context limitations.
