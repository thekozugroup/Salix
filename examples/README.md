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
