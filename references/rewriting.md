# Rewriting

Improve how the draft sounds without changing what it says. Use measurements
to choose small edits; the assistant, not the CLI, performs the rewrite.

## Establish Inputs

1. Identify the draft, intended audience, named profile, and resolved store.
   Read [Setup And Profiles](setup.md) if the chosen profile is missing or the
   store is ambiguous. Confirm status/comparison provenance, including any
   same-name global fallback, then pin the selected store with `--home`.
   Do not substitute a different profile name.
2. Preserve the original raw text, including Markdown and protected spans.
   Use a separate candidate file unless an in-place edit was explicitly
   requested. For pasted text, use a private, unique working location; avoid
   predictable shared `/tmp` filenames.
3. Record constraints: claims and qualifications, names, numbers/units/dates,
   quotations, code, URLs, citations, headings, and section order. Explicit user
   content changes are separate from voice matching and must be reported.

Use actual absolute paths for `ORIGINAL`, `CANDIDATE`, and `FINAL`. Keep the
original project working directory and selected `PROFILE_HOME` throughout.

```bash
python3 "$SALIX_CLI" analyze "$ORIGINAL" --json --pretty
python3 "$SALIX_CLI" compare "$ORIGINAL" --profile "$PROFILE" --home "$PROFILE_HOME" --json --pretty
```

Retain these results as the baseline. Empty or mostly code-only analysis is not
usable prose evidence. A short email may be rewritten conservatively, but its
features are noisy; do not claim high-confidence voice matching.

## Bounded Host Edit Loop

Default budget: up to six host edit passes, fewer when requested. `compare` has
no `--max-iter` or `--threshold` flags; the host manages this budget.

For each pass:

1. Read `top_gaps` and select up to three safe, relevant changes. Use
   `feature`, `direction`, `target`, and `benchmark`; `edit_hint` is advisory.
2. Edit only the needed prose. Prefer cadence, punctuation, sentence boundaries,
   or existing transitions. Do not replace paragraphs wholesale unless the
   user explicitly asks for a broader rewrite.
3. Review the raw diff before scoring. Reject changes to protected material,
   factual meaning, certainty, causality, or the author's intended emphasis.
4. Save the candidate and run the same `compare` command on that exact file.
   Track actual score, host pass number, and quality notes. Keep the best
   meaning-preserving, readable candidate, including the untouched original.

```bash
python3 "$SALIX_CLI" compare "$CANDIDATE" --profile "$PROFILE" --home "$PROFILE_HOME" --json --pretty
```

Examples of unsafe metric chasing: removing "may" from a qualified claim,
adding "clearly" to uncertain evidence, padding sentences with filler, changing
specialist terms for lexical variety, or inserting rhetorical questions that
alter emphasis. Skip such hints even when they rank first. Character-fragment
gaps do not justify copying topic vocabulary or the sample's content.

## Stop

Stop at the first applicable condition:

- No safe, useful changes remain, or readability/meaning is getting worse.
- Two consecutive passes do not improve the best safe distance by more than
  0.001. This is a practical plateau rule, not a significance test.
- The six-pass budget or the user's smaller budget is exhausted.
- An agreed numeric stopping target is reached. If 0.15 is used, label it a
  heuristic; it is not a validated universal cutoff or guaranteed outcome.
- A runtime error prevents reliable comparison. Explain the failure; only
  continue with an explicitly unmeasured qualitative rewrite when appropriate.

Do not keep degrading prose to reach a number. A lower score alone is not a
reason to retain an edit. Keep the best safe candidate and state when the score
did not improve or the original remained best. Count actual edit passes, not
CLI calls or simulator history entries.

## Final Checks And Report

Review the raw original/final diff. Verify exact protected strings and the
unchanged values and associations of every number, unit, date, and named fact.
Read for meaning, qualifiers, negation, chronology, causality, formatting, and
section order. State checks actually performed; the CLI does not prove them.

Measure the exact selected final file again:

```bash
python3 "$SALIX_CLI" analyze "$FINAL" --json --pretty
python3 "$SALIX_CLI" compare "$FINAL" --profile "$PROFILE" --home "$PROFILE_HOME" --json --pretty
```

Follow [Validation And Reporting](validation.md). Lead with whether the rewrite
is ready and any unresolved limitations. Include output path, profile/store,
before/after distance, actual passes, stopping reason, and quality checks. Only
add feature deltas that were measured. Failed measurements are "unmeasured",
not zero. If selecting an earlier candidate, report that file's fresh result,
not the last attempted pass's score.

## Optional Simulation

`simulate` is a rule-based mechanics experiment, not the host rewrite workflow.
Run it only when requested or when diagnosing loop behavior, on a scratch copy.

```bash
python3 "$SALIX_CLI" simulate "$SCRATCH" --profile "$PROFILE" --home "$PROFILE_HOME" --max-iter 6 --threshold 0.15 --json --pretty
```

Prefer `--json` without verbose logging; older versions can mix verbose text
into stdout. Do not use `--out` on the user's original. The simulator operates
on cleaned text, may remove
formatting/protected material, and can change meaning. Remeasure the actual
saved output rather than infer its final score from the last history entry.
Simulator progress does not validate human voice, content preservation, or a
real assistant rewrite.
