# Examples

`example_benchmark.json` is a Salix benchmark generated from the project's own
documentation (README.md, SKILL.md, CHANGELOG.md). Use it to inspect what a
real benchmark file looks like, including the `_sigma` empirical-variance
section and the topic-blind n-gram lists.

```bash
./salix benchmark --profile example   # if symlinked into benchmarks/
# or
python3 scripts/visualize.py examples/example_benchmark.json
```

It is not intended as a "default style" — it just shows the file format.

## Prompt comparison

Prompt:

```text
Write a short note explaining why focused work matters.
```

| Full AI-generated draft | Salix-stylized draft |
| --- | --- |
| Focused work matters because it gives people the time and attention needed to do meaningful thinking. In a noisy environment, priorities blur and progress becomes reactive. A focused block creates space to solve the real problem, make better decisions, and finish work with less waste. | Focus is not magic. It is just the condition where the real work finally has enough room to show itself. When the day gets chopped into little pieces, every decision starts arriving half-formed. A quiet block changes that. It lets the important problem sit in front of you long enough to become specific, and once it is specific, it usually becomes smaller. |

This is an illustrative product demo, not a universal guarantee. A real Salix
pass depends on the user's benchmark, the draft, the threshold, and whether the
edit loop plateaus before convergence.

## Recursive edit convergence

Salix tracks distance after each edit pass. Lower is closer to the selected
profile.

```text
iter  distance  top_gap             chart
----  --------  ------------------  ------------------------
0     2.184     mean_sent_len       ########################
1     1.622     punct_comma_per1k   ##################
2     1.087     hedging_rate        ############
3     0.641     discourse_rate      #######
4     0.413     comma_per_sentence  #####
```

Create local chart data:

```bash
./salix simulate draft.md --profile default --scope auto --json --pretty > convergence.json
python3 scripts/visualize.py convergence.json
```
