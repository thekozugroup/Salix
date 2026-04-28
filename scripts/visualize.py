#!/usr/bin/env python3
"""Render a stats blob or gap report as ASCII tables for human review.

Usage:
    python3 scripts/visualize.py benchmarks/default.json
    python3 scripts/visualize.py /tmp/salix_target.stats.json
    python3 scripts/visualize.py /tmp/salix_gap.json    # auto-detects gap report
"""

from __future__ import annotations

import _path  # noqa: F401
import argparse
import json
import sys
from pathlib import Path


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    sep = "  ".join("-" * w for w in widths)
    out = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)), sep]
    for r in rows:
        out.append("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))
    return "\n".join(out)


def _is_gap_report(d: dict) -> bool:
    return "total_distance" in d and "top_gaps" in d


def _is_benchmark(d: dict) -> bool:
    return "stats" in d and isinstance(d.get("stats"), dict)


def render_stats(stats: dict, header: str = "STATS") -> str:
    sections: dict[str, list] = {
        "Lexical": ["word_count", "type_count", "ttr", "mtld",
                    "mean_word_len", "long_word_ratio"],
        "Sentence shape": ["sentence_count", "mean_sent_len", "stdev_sent_len",
                           "max_sent_len", "short_sent_ratio", "long_sent_ratio",
                           "comma_per_sentence"],
        "Readability": ["flesch_kincaid_grade", "gunning_fog", "ari"],
        "Tone": ["formality_f_score", "passive_per1k", "hedging_rate",
                 "booster_rate", "discourse_rate", "positive_rate",
                 "negative_rate", "sentiment_polarity"],
        "Paragraph": ["paragraph_count", "mean_paragraph_sents", "mean_paragraph_words"],
    }
    out = [f"\n=== {header} ==="]
    for sect, keys in sections.items():
        rows = []
        for k in keys:
            if k in stats:
                rows.append([k, f"{stats[k]:.3f}" if isinstance(stats[k], float) else str(stats[k])])
        if rows:
            out.append(f"\n[{sect}]")
            out.append(_table(rows, ["feature", "value"]))

    # Punctuation
    punct_rows = [[k.replace("punct_", "").replace("_per1k", ""),
                   f"{v:.3f}"] for k, v in sorted(stats.items())
                  if k.startswith("punct_")]
    if punct_rows:
        out.append("\n[Punctuation per 1k words]")
        out.append(_table(punct_rows, ["mark", "rate"]))

    # Top function words
    fw_rows = sorted(
        ((k.replace("fw_", "").replace("_per1k", ""), v)
         for k, v in stats.items() if k.startswith("fw_") and k.endswith("_per1k")),
        key=lambda x: -x[1],
    )[:20]
    if fw_rows:
        out.append("\n[Top function words per 1k]")
        out.append(_table([[w, f"{v:.2f}"] for w, v in fw_rows], ["word", "rate"]))

    # n-grams
    for key, label in [("fw_bigrams", "Function-word bigrams"),
                       ("fw_trigrams", "Function-word trigrams"),
                       ("sentence_starters", "Sentence starters")]:
        items = stats.get(key, [])
        if items:
            out.append(f"\n[{label} (top)]")
            out.append(_table([[g, f"{f:.4f}"] for g, f in items[:10]], ["item", "freq"]))

    return "\n".join(out)


def render_gap(report: dict) -> str:
    out = [f"\n=== STYLE GAP REPORT (total distance: {report['total_distance']}) ==="]

    cats = report.get("category_summary", {})
    if cats:
        rows = [[c, f"{v['avg_z']:.3f}", f"{v['weight']:.2f}", f"{v['weighted']:.3f}"]
                for c, v in sorted(cats.items(), key=lambda x: -x[1]["weighted"])]
        out.append("\n[Category breakdown]")
        out.append(_table(rows, ["category", "avg_z", "weight", "weighted"]))

    top_gaps = report.get("top_gaps", [])
    if top_gaps:
        out.append("\n[Top 10 feature gaps]")
        rows = [[g["feature"], g["category"], f"{g['target']:.3f}",
                 f"{g['benchmark']:.3f}", f"{g['z_distance']:+.2f}"]
                for g in top_gaps]
        out.append(_table(rows, ["feature", "category", "target", "bench", "z"]))

    ng = report.get("ngram_gaps", {})
    for k, v in ng.items():
        out.append(f"\n[{k} distribution distance: {v['distance']:.4f}]")
        if v["top_divergent"]:
            rows = [[d["item"], f"{d['target']:.4f}", f"{d['benchmark']:.4f}",
                     f"{d['delta']:.4f}"] for d in v["top_divergent"][:6]]
            out.append(_table(rows, ["pattern", "target", "bench", "Δ"]))

    if top_gaps:
        out.append("\n[Top 3 actionable edits]")
        for i, g in enumerate(top_gaps[:3], 1):
            out.append(f"  {i}. {g['suggestion']}")
            if g.get("edit_hint"):
                out.append(f"     → {g['edit_hint']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Salix stats or gap report as tables.")
    ap.add_argument("path", help="Path to a stats, benchmark, or gap-report JSON")
    args = ap.parse_args()

    data = json.loads(Path(args.path).read_text())
    if _is_gap_report(data):
        print(render_gap(data))
    elif _is_benchmark(data):
        print(f"\nBenchmark: {data.get('name', '?')}  ({data['stats'].get('total_word_count', 0):,} words from {data['stats'].get('sample_count', '?')} samples)")
        print(render_stats(data["stats"], header=f"BENCHMARK '{data.get('name', '?')}'"))
    else:
        print(render_stats(data, header="TARGET STATS"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
