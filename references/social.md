# Social references and draft review

Use `./salix social` from the installed skill directory. All commands run locally;
no network, posting, or LLM service is built in. The host LLM writes and edits.
Salix measures text; it does not fine-tune a model. Existing document commands and
their default 300-word minimum remain unchanged.

## Capture input

`social ingest INPUT.json --out-dir REFERENCES [--metrics-only]` accepts one record
or an array. These fields describe one attributable source, not a research summary:

```json
{
  "schema_version": 1,
  "id": "sample-post-1",
  "author_id": "sample-author",
  "source_url": "https://example.org/posts/1",
  "source_type": "original_post",
  "retrieved_at": "2026-01-01T12:00:00Z",
  "published_at": "2025-12-20",
  "capture_method": "original public page",
  "measured_from": "original_text",
  "text_complete": true,
  "original_text": "We tested the idea. Then we wrote down what changed.",
  "excerpt": "We tested the idea.",
  "summary": "Researcher's summary, excluded from measurements.",
  "metrics": {"reactions": 12, "comments": 2, "reposts": null, "impressions": null, "followers": null},
  "confounds": ["Public counters observed at retrieval time; exposure unknown."]
}
```

`id` is optional (a source/author hash is generated). Author and record IDs must
be lowercase slugs. `published_at` is optional; use null if unknown. Excerpts are
optional and limited to 25 whitespace-delimited words per record; obey any stricter
source/use-specific quotation limit. Other metadata is preserved but never analyzed.
Keep full bodies out of metadata. No excerpt is generated automatically.

An original post is eligible only with `measured_from: "original_text"` and
`text_complete: true`. The author identity and completeness are capture
attestations; inspect the source. A repost's isolated author's caption can be used
only with `source_type: "repost"`, `measured_from: "original_caption"`,
`text_complete: true`, and `attribution_verified: true`. Do not count the shared
post as the caption. Comments, summaries, incomplete text, and all other repost
bodies remain reference-only even when a stats dictionary is supplied. If authorship
or boundaries are unclear, keep the record ineligible. One word is accepted for an
eligible original; accepting it is not evidence that its style is representative.

The command writes `REFERENCES/AUTHOR/ID.post.json` and a source-linked `.md` file.
Markdown visibly separates metadata from captured prose. Legacy text loaders reject
these marked reference files so their headings/summaries cannot enter a benchmark.
Use the paired JSON with `social profile`. Existing files are not overwritten;
use a new capture directory for refreshed measurements. Duplicate IDs, URLs or
body hashes within an author are excluded; conflicting authors for one URL error.

## Metrics-only capture without retaining a full body

Use `--metrics-only` to omit `original_text` from output after measuring it with
`lib.stats.analyze`. Input bodies already saved to disk are not erased. For a
capture process that never writes the original body, run in memory:

```python
from hashlib import sha256
from lib.stats import analyze
record["stats"] = analyze(original_body)
record["body_sha256"] = sha256(original_body.encode("utf-8")).hexdigest()
# Add provenance fields above, then persist record without original_text.
```

Pass this JSON to the same ingest command. External measurements require
`capture_method`, a 64-character lowercase SHA256 `body_sha256`, and exactly the
raw `analyze` feature keys with finite numeric values. Do not supply an aggregate,
invented feature values, or a summary's measurements. Schema validation cannot
prove where metrics came from or that a digest matches unavailable source text.
Stored external records say `external_lib.stats.analyze_attestation`. Hashes support
identification/deduplication, not source authentication. Metrics retain short n-grams
and sentence starters: metrics-only is not a guarantee of anonymization or secrecy.

Social analysis passes the exact supplied body to `analyze`, preserving paragraphs;
it does not run the legacy Markdown cleaner. Exclude platform chrome, retrieval
labels, comments, shared bodies and researcher commentary before calling it. It is
still heuristic tokenization (e.g. URLs may affect counts), not perfect parsing.

## Profiles and comparisons

```sh
./salix social profile REFERENCES --out profiles.json
./salix social compare profiles.json --out chart-data.json
```

Profile input may also be a JSON record or array. Each author gets their own raw
per-post stats and a `lib.stats.aggregate` result. Missing/excluded authors have
empty stats, zero samples, and remain provisional. Default sufficiency floors are
10 distinct posts AND 3,000 words. Configure `--min-posts` and `--min-words`; these
are heuristic floors, not a validated stability test. A profile below either is
`provisional`; above both it is `descriptive`, never declared a trained model.
Counts and limits remain in the output. Do not silently merge authors into a
personal profile. Profiles themselves omit full original bodies.

The comparison JSON has `authors` (aggregate stats, sufficiency, status) and
long-form `rows` (`author_id`, `post_id`, `source_url`, `metric`, `value`, `kind`,
`profile_status`). These rows are suitable for grouped bars, distributions or
scatterplots. `_per1k` means occurrences per 1,000 words; ratios are fractions;
raw counts retain their count units. Aggregate scalar features are Salix's
word-weighted per-post means; `total_word_count` and `sample_count` are totals.
Within-author sigma is descriptive spread, not a confidence interval. Missing
public counts stay null, never zero. Use visible caveats for short samples,
selection bias, English-oriented heuristics, mixed topics and optional NLP backend
variation. There is no engagement score, causal claim or prediction.

## Review a draft

The host writes a fresh draft using broad reference characteristics while preserving
the intended speaker, facts and topic. A reference author's prose is not evidence
for claims about the user's product. Check claims against authorized sources.

```sh
./salix social review draft.md --policy review-policy.json --out review.json
```

Example policy (replace the hash with the current UTF-8 draft's SHA256):

```json
{
  "excluded_terms": ["unreleased project", "guaranteed results"],
  "draft_sha256": "current-draft-sha256",
  "factual_state": "needs_review",
  "approval_state": "draft",
  "claims": [{"claim": "A claim needing evidence.", "status": "unverified"}]
}
```

Excluded terms use Unicode normalization, case-insensitive matching, word boundaries
and flexible whitespace between phrase words; substrings inside unrelated words do
not match. This is a literal phrase check, not semantic paraphrase detection.
Factual states: `unverified`, `needs_review`, `verified`. Approval states: `draft`,
`needs_review`, `approved`, `rejected`. Claims use `unverified`, `verified`, or
`rejected`; a verified claim requires an `evidence` string (source link or evidence
location). Record the user's actual approval; never infer it from stylistic quality.

The command returns 1 with a report for blockers, 0 when recorded checks pass.
Any edit changes the draft digest and invalidates the recorded states. No automatic
fact verification, claim extraction/coverage check or identity verification occurs;
passing means the supplied attestations and exclusions pass, not permission to post.
The workflow never publishes. Follow the user's actual publication authorization.
