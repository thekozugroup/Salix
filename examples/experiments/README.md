# Experiment Archive

`harness-v1.json` contains two real baseline outputs and 16 recorded Codex rewrite
attempts. Attempt 17 was interrupted during a model call after independent review
found harness defects. The old harness did not preserve that partial call. No
partial output, usage, or duration is reconstructed.

The original generator is recoverable from commit `a6f56c0`; its hash is recorded
in the JSON. Stored texts and selection history are unchanged. Only the archive's
completion status and audit note identify the stop.

Known limitations: environment inheritance, incomplete tool detection, lexical
apostrophe normalization, an ineligible starting draft, and incomplete failure
recording. No actual credential leak or model tool use was observed in recorded
outputs. This archive is not the hardened experiment or proof of convergence.
