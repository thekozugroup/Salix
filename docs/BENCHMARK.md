# Recorded Writing Experiment

This is a real model experiment with local measurement checks, not a claim of
perfect voice matching. All baseline and candidate texts, prompts, hashes,
settings, usage counters, and scores are retained in
[live_convergence.json](../examples/live_convergence.json).

## Conditions

One configured Codex model, `gpt-5.6-sol`, with low reasoning effort, generated:

1. The base prompt alone.
2. The same prompt plus "Write in the style of Arthur Conan Doyle's Sherlock Holmes stories."
3. Successive rewrites of the base draft using Salix measurements and training samples.

The fixed task is a 400-550-word first-person Watson case note. Clara Bell's
return ticket is missing; her Euston train leaves at 6:40; rain and a folded
newspaper's dry interior lead Holmes to the ticket. There is no theft or culprit.
The complete executable prompt is in every relevant model-call record.

Watson and Baker Street already cue Doyle in the base condition. Baselines are
generated once, not repeatedly sampled controls. Codex supplies a shared host
system context; empty home directories do not establish a bare-model control.
Requested model/settings are local execution metadata, not provider-signed
attestation or a captured full system prompt.

## Corpus

The canonical text is [The Adventures of Sherlock Holmes](https://www.gutenberg.org/cache/epub/1661/pg1661.txt).
The first complete paragraphs totaling at least 500 whitespace words from each
of the first six stories are selected deterministically:

| Training | Held Out |
| --- | --- |
| A Scandal in Bohemia | The Red-Headed League |
| A Case of Identity | The Boscombe Valley Mystery |
| The Five Orange Pips | The Man with the Twisted Lip |

Each passage is analyzed separately, then aggregated using the production
word-weighted profile builder. No passage is repeated to simulate more evidence.
The held-out scores never enter model prompts, feedback, or numerical ranking.
An eight-word lexical overlap check uses both splits to veto direct copying,
so held-out text does influence eligibility. This is not a completely untouched
test set. Model pretraining may already contain the book.

Opening excerpts have more long narration than a dialogue-heavy case note.
Topic, length, format, and within-author variation affect these metrics. Three
excerpts per split from one book do not represent all of Doyle's writing.

## Selection And Charts

Each new candidate receives the same factual task, the training passages, and
six measured scalar gaps. The harness retains a candidate only if it passes
mechanical screens and improves the training distance, or if no eligible
starting draft exists. Whitespace word counts enforce the requested length;
Salix's cleaned tokenizer reports a separate word count.

The grey line shows every completed candidate, including rejected ones. Blue
shows the retained draft. Base and explicit-style results are constant lines;
green is the author-profile reference. Scalar charts show values; distribution
charts show distance, not raw frequency lists. Unavailable POS features show
no match line. [All variable charts](../examples/live_convergence_charts/README.md)
are separate from the main README overview.

The fifty-attempt budget exposes repeated setbacks and plateaus. It is not a
zero-distance stopping target. Production skill guidance instead caps work at
six safe passes and stops after two consecutive passes without useful progress.
A lower score alone is not enough to retain a production rewrite.

## Recorded Result

The completed run contains two baselines and fifty real rewrite attempts.
Only attempts 1 and 35 were retained. The final selected text is call 36, not
the last generated candidate. No failed calls are reported in this hardened run.

| Condition | Training Distance | Held-Out Distance |
| --- | ---: | ---: |
| Base prompt | 2.4416 | 1.1912 |
| Explicit style prompt | 2.3801 | 1.1403 |
| Retained Salix-feedback draft | 2.1400 | 1.1057 |

These improvements are descriptive results from one run, without confidence
intervals or a significance claim. The author-profile reference is not reached.
Most attempts regress or fail a screen; the retained line is selected data and
must not replace the raw candidate line.

Token checks do not prove the associations, reasoning, chronology, certainty,
or overall quality of a story. Independent reading is required. A dry newspaper
does not logically prove the ticket's location; candidate narratives can
overstate that clue. Metric improvements are not writing-quality grades.
Independent review of both baselines and selected call 36 found the fixed facts
preserved, but an unjustified certainty that the ticket must have been inserted
before exposure to rain. Sheltered later insertion remains possible. The selected
draft's prose is readable; overall superiority is not established.

## Reproduce

Offline checks make no model calls:

```bash
python3 scripts/live_convergence.py --validate examples/live_convergence.json
python3 scripts/render_live_convergence.py
python3 -m unittest discover -s tests -p 'test_live*.py'
```

Validation remeasures exact stored text, verifies hashes and corpus aggregation,
and replays selection and prompt history. It does not authenticate a JSON file
as a provider-issued log. The run uses deterministic fallback syllables and
formality; spaCy POS is unavailable. Installing optional backends does not change
the explicitly selected fallback used to verify this record.

A new run consumes your logged-in Codex account and may take many minutes:

```bash
python3 scripts/live_convergence.py --run --attempts 50 --out examples/new-experiment.json
```

The runner refuses to overwrite an existing record. It isolates home/project
directories, allows only a small environment set, disables optional tool
features, rejects unknown tool items, and retains sanitized failure records.
Known secret patterns and environment secrets are redacted; no redacted output
is scored. These protections are not proof against every conceivable leak.
Sampling is stochastic; a fresh run need not reproduce these prose outputs.

The earlier, weaker harness stopped after 16 recorded attempts. Its unchanged
drafts and disclosed unrecorded interruption remain in the
[experiment archive](../examples/experiments/README.md), not pooled into this run.

## Remaining Evidence

Repeat with multiple authors, prompts, genres, model seeds/settings, and matched
held-out samples. Add blinded human quality comparisons, stronger semantic
preservation checks, and genre-aware profile selection before making broad
superiority or voice-fidelity claims. Neither this run nor passing tests justify
universal 100% grades.
