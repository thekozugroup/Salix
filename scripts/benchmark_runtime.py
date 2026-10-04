#!/usr/bin/env python3
"""Measure warm analyze() latency; optionally compare an unchanged Git revision.

Example: python3 scripts/benchmark_runtime.py --baseline-ref 65b6f59
The baseline is loaded in memory. No checkout, files, or optional dependencies
are modified. Baseline and current features must match before timing begins.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import time
import warnings
from pathlib import Path
from types import ModuleType

import _path  # noqa: F401

from lib import stats

ROOT = Path(__file__).resolve().parent.parent
PARAGRAPH = (
    "The implications of this shift are, perhaps, more subtle than they first appear. "
    "One could argue that the architecture itself imposes constraints; indeed, those "
    "constraints shape the resulting style. The author writes deliberately, choosing "
    "each subordinate clause with care. Rather than rush, the prose unfolds slowly, "
    "turning over each idea before committing it to the page."
)
WORKLOADS = {
    "short_draft": PARAGRAPH,
    "many_paragraphs": "\n\n".join([PARAGRAPH] * 250),
    "long_repeated": "This is sentence number one. This is sentence number two. " * 2500,
}


def load_baseline(ref: str) -> ModuleType:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    source = subprocess.run(
        ["git", "show", f"{resolved}:lib/stats.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    module = ModuleType("lib._runtime_baseline")
    module.__package__ = "lib"
    module.__file__ = f"{resolved}:lib/stats.py"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    module.baseline_ref = resolved
    return module


def time_analysis(module: ModuleType, text: str, number: int) -> float:
    start = time.perf_counter()
    for _ in range(number):
        module.analyze(text)
    return (time.perf_counter() - start) / number


def summarize(samples: list[float]) -> dict:
    return {
        "median_ms": round(statistics.median(samples) * 1000, 4),
        "min_ms": round(min(samples) * 1000, 4),
        "max_ms": round(max(samples) * 1000, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", help="Git commit/ref supplying baseline lib/stats.py")
    parser.add_argument("--repeat", type=int, default=7, help="Timing batches per workload")
    parser.add_argument("--number", type=int, default=5, help="Analyses per timing batch")
    parser.add_argument("--pos-backend", choices=["proxy", "auto"], default="proxy")
    args = parser.parse_args()
    if args.repeat < 1 or args.number < 1:
        parser.error("--repeat and --number must be positive")

    baseline = load_baseline(args.baseline_ref) if args.baseline_ref else None
    modules = {"current": stats}
    if baseline is not None:
        modules["baseline"] = baseline
    if args.pos_backend == "proxy":
        for module in modules.values():
            module._get_spacy_nlp = lambda: None

    results = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        # Warm optional loaders/caches and verify every feature before any timing.
        for name, text in WORKLOADS.items():
            current_features = stats.analyze(text)
            if baseline is not None and baseline.analyze(text) != current_features:
                raise RuntimeError(f"Feature mismatch on {name}; refusing a misleading timing")
            for module in modules.values():
                module.analyze(text)

        for name, text in WORKLOADS.items():
            timings: dict[str, list[float]] = {label: [] for label in modules}
            for repetition in range(args.repeat):
                order = list(modules.items())
                if repetition % 2:
                    order.reverse()
                for label, module in order:
                    timings[label].append(time_analysis(module, text, args.number))
            entry = {"workload": name, "characters": len(text),
                     "words": len(stats.tokenize(text)),
                     **{label: summarize(samples) for label, samples in timings.items()}}
            if baseline is not None:
                before = statistics.median(timings["baseline"])
                after = statistics.median(timings["current"])
                entry["speedup"] = round(before / after, 3)
                entry["time_reduction_pct"] = round((1 - after / before) * 100, 2)
            results.append(entry)

    print(json.dumps({
        "python": platform.python_version(),
        "platform": platform.platform(),
        "baseline_ref": baseline.baseline_ref if baseline is not None else None,
        "baseline_scope": "lib/stats.py with current lib dependencies",
        "pos_backend": stats.analyze(PARAGRAPH)["formality_source"],
        "syllable_backend": "pyphen" if stats._PYPHEN_DIC is not None else "vowel_proxy",
        "warmup_analyses_per_workload": 2,
        "repeat": args.repeat,
        "number": args.number,
        "features_equal": True if baseline is not None else None,
        "results": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
