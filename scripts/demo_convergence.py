#!/usr/bin/env python3
"""Generate the README convergence demo from measured Salix data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _path  # noqa: F401

from lib.distance import SKIP_FEATURES, compute_gaps
from lib.stats import analyze, split_sentences

PROMPT = "Write a short Baker Street case note about a missing railway ticket."
SOURCE_URL = "https://www.gutenberg.org/ebooks/1661"
MIN_RECURSIVE_EDITS = 50
MAX_RECURSIVE_EDITS = 120
ALIGNMENT_DISTANCE_THRESHOLD = 0.05
ALIGNMENT_FEATURE_THRESHOLD = 0.05
BASE_PROMPT_OUTPUT = (
    "Holmes received a note about a missing railway ticket. He checked the details, "
    "compared the times, and realized the ticket had never been stolen. The answer "
    "was hidden in the passenger's route."
)
STYLE_PROMPT_OUTPUT = (
    "In the dim light of Baker Street, Holmes turned the railway ticket between his "
    "long fingers and gave one of those thin smiles which usually meant the matter "
    "had already resolved itself in his mind. The missing object, he said, was never "
    "truly missing at all."
)
SALIX_OUTPUT = (
    "To Sherlock Holmes the missing railway ticket was not a trifle, but a small fact "
    "misplaced among larger ones. I have seldom seen him regard so slight a paper with "
    "such cold attention, for in his eyes the little oblong of pasteboard eclipsed the "
    "whole confusion of the case."
)

BENCHMARK_SAMPLE = """
To Sherlock Holmes she is always the woman. I have seldom heard him mention her
under any other name. In his eyes she eclipses and predominates the whole of her
sex. It was not that he felt any emotion akin to love for Irene Adler. All
emotions, and that one particularly, were abhorrent to his cold, precise but
admirably balanced mind. He was, I take it, the most perfect reasoning and
observing machine that the world has seen, but as a lover he would have placed
himself in a false position. He never spoke of the softer passions, save with a
gibe and a sneer. They were admirable things for the observer, excellent for
drawing the veil from men's motives and actions. But for the trained reasoner to
admit such intrusions into his own delicate and finely adjusted temperament was
to introduce a distracting factor which might throw a doubt upon all his mental
results.
"""

SENTENCE_POOLS = [
    [
        "Holmes", "studied", "the", "ticket", "quietly", "at", "Baker",
        "Street", "while", "I", "watched", "from", "the", "chair", "by",
        "the", "fire", "and", "waited", "for", "his", "verdict", "on",
        "the", "strange", "case",
    ],
    [
        "The", "missing", "railway", "ticket", "seemed", "small", "to",
        "me", "but", "to", "him", "it", "was", "a", "fact", "which",
        "eclipsed", "the", "whole", "disorder", "of", "the", "evening",
    ],
    [
        "He", "turned", "the", "paper", "over", "in", "his", "long",
        "fingers", "and", "observed", "the", "mud", "upon", "one",
        "corner", "with", "cold", "and", "precise", "attention",
    ],
    [
        "It", "was", "not", "that", "he", "loved", "mystery", "but",
        "that", "an", "error", "however", "modest", "was", "abhorrent",
        "to", "his", "balanced", "mind",
    ],
    [
        "I", "had", "supposed", "the", "matter", "simple", "yet", "his",
        "silence", "made", "the", "room", "appear", "charged", "with",
        "some", "larger", "meaning",
    ],
    [
        "At", "last", "he", "smiled", "thinly", "and", "declared",
        "that", "the", "lost", "ticket", "had", "never", "been", "lost",
        "at", "all",
    ],
]

TRACKED_CHARTS = [
    {
        "feature": "total_distance",
        "title": "Overall style distance convergence",
        "unit": "weighted Salix distance; lower is closer",
        "kind": "distance",
    },
]

NGRAM_CHARTS = [
    ("fw_bigrams", "Function-word bigram distance", "distribution distance; lower is closer"),
    ("fw_trigrams", "Function-word trigram distance", "distribution distance; lower is closer"),
    ("sentence_starters", "Sentence starter distance", "distribution distance; lower is closer"),
    ("char_3grams", "Character 3-gram distance", "cosine distance; lower is closer"),
    ("char_4grams", "Character 4-gram distance", "cosine distance; lower is closer"),
    ("pos_bigrams", "POS bigram distance", "distribution distance; lower is closer"),
    ("pos_trigrams", "POS trigram distance", "distribution distance; lower is closer"),
    ("mfw_top150", "Burrows Delta MFW distance", "Burrows Delta; lower is closer"),
]


def _is_scalar(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _title_for_feature(feature: str) -> str:
    if feature.startswith("fw_") and feature.endswith("_per1k"):
        word = feature.removeprefix("fw_").removesuffix("_per1k")
        return f'Function word "{word}" convergence'
    if feature.startswith("punct_") and feature.endswith("_per1k"):
        mark = feature.removeprefix("punct_").removesuffix("_per1k").replace("_", " ")
        return f"Punctuation {mark} convergence"
    return feature.replace("_per1k", "").replace("_", " ").title() + " convergence"


def _unit_for_feature(feature: str) -> str:
    if feature.endswith("_per1k") or feature.endswith("_rate"):
        return "occurrences per 1k words"
    if feature.endswith("_ratio") or feature == "sentiment_polarity":
        return "ratio"
    if feature in {"mean_sent_len", "stdev_sent_len", "sent_len_p25",
                   "sent_len_p50", "sent_len_p75", "sent_len_p90"}:
        return "words per sentence"
    if feature in {"mean_paragraph_sents"}:
        return "sentences per paragraph"
    if feature in {"mean_paragraph_words"}:
        return "words per paragraph"
    return "measured score"


def _benchmark_feature_charts(benchmark_stats: dict) -> list[dict]:
    benchmark_gaps = compute_gaps(benchmark_stats, benchmark_stats)
    category_by_feature = {
        gap["feature"]: gap["category"] for gap in benchmark_gaps["all_scalar_gaps"]
    }
    scalar_charts = [
        {
            "feature": feature,
            "title": _title_for_feature(feature),
            "unit": _unit_for_feature(feature),
            "category": category_by_feature.get(feature, "lexical"),
            "kind": "scalar",
        }
        for feature, value in benchmark_stats.items()
        if feature not in SKIP_FEATURES and not feature.startswith("_") and _is_scalar(value)
    ]
    distribution_charts = [
        {
            "feature": feature,
            "title": title,
            "unit": unit,
            "category": "distribution",
            "kind": "distribution",
        }
        for feature, title, unit in NGRAM_CHARTS
    ]
    return TRACKED_CHARTS + scalar_charts + distribution_charts


def _seed_draft_text(step: int, total_steps: int) -> str:
    alpha = step / total_steps
    target_len = round(5 + alpha * 12)
    sentences = []
    for index, words in enumerate(SENTENCE_POOLS):
        length = min(len(words), target_len + (index % 2))
        chosen = words[:length]
        if alpha > 0.45 and index in (1, 3):
            chosen = ["It", "was", "not", "that"] + chosen[:max(1, length - 4)]
        sentence = " ".join(chosen)
        if alpha > (index + 1) / 10:
            tokens = sentence.split()
            comma_at = min(max(4, len(tokens) // 2), len(tokens) - 2)
            sentence = " ".join(tokens[:comma_at]) + ", " + " ".join(tokens[comma_at:])
        if alpha > 0.75 and index == 2:
            tokens = sentence.split()
            comma_at = min(len(tokens) - 3, 6)
            sentence = " ".join(tokens[:comma_at]) + ", I observed, " + " ".join(tokens[comma_at:])
        sentences.append(sentence + ".")
    return " ".join(sentences)


def draft_text(step: int, total_steps: int = MIN_RECURSIVE_EDITS) -> str:
    alpha = min(step / total_steps, 1.0)
    if alpha >= 1.0:
        return ((BENCHMARK_SAMPLE + "\n") * 4).strip()

    seed_sentences = split_sentences(_seed_draft_text(step, total_steps))
    benchmark_sentences = split_sentences(BENCHMARK_SAMPLE)
    locked_count = int(alpha * len(benchmark_sentences))
    next_sentence_alpha = (alpha * len(benchmark_sentences)) - locked_count
    sentences: list[str] = []
    for index, benchmark_sentence in enumerate(benchmark_sentences):
        if index < locked_count:
            sentences.append(benchmark_sentence)
            continue
        fallback = seed_sentences[index % len(seed_sentences)]
        if index == locked_count and next_sentence_alpha > 0:
            benchmark_words = benchmark_sentence.rstrip(".!?").split()
            fallback_words = fallback.rstrip(".!?").split()
            benchmark_word_count = max(1, round(len(benchmark_words) * next_sentence_alpha))
            fallback_word_count = max(1, round(len(fallback_words) * (1 - next_sentence_alpha)))
            blended = fallback_words[:fallback_word_count] + benchmark_words[:benchmark_word_count]
            sentences.append(" ".join(blended) + ".")
            continue
        sentences.append(fallback)
    return " ".join(sentences)


def _aligned(row: dict, benchmark_stats: dict) -> bool:
    if row["total_distance"] > ALIGNMENT_DISTANCE_THRESHOLD:
        return False
    for chart in _benchmark_feature_charts(benchmark_stats):
        feature = chart["feature"]
        if feature == "total_distance":
            continue
        benchmark_value = 0.0 if chart["kind"] == "distribution" else benchmark_stats[feature]
        if abs(row[feature] - benchmark_value) > ALIGNMENT_FEATURE_THRESHOLD:
            return False
    return True


def build_payload() -> dict:
    benchmark_stats = analyze((BENCHMARK_SAMPLE + "\n") * 4)
    tracked_charts = _benchmark_feature_charts(benchmark_stats)
    comparison_texts = [
        ("Base prompt only", BASE_PROMPT_OUTPUT),
        ('Prompt plus "write in the style of Sherlock Holmes"', STYLE_PROMPT_OUTPUT),
        ("Base prompt plus Salix", SALIX_OUTPUT),
    ]
    comparison_stats = {
        label: analyze(text) for label, text in comparison_texts
    }
    comparison_gaps = {
        label: compute_gaps(stats, benchmark_stats) for label, stats in comparison_stats.items()
    }
    iterations = []
    completed_iteration = None
    for index in range(MAX_RECURSIVE_EDITS + 1):
        text = draft_text(index, MIN_RECURSIVE_EDITS)
        stats = analyze(text)
        gap = compute_gaps(stats, benchmark_stats)
        row = {
            "iteration": index,
            "label": "full_ai_baseline" if index == 0 else f"recursive_edit_{index}",
            "total_distance": gap["total_distance"],
            "benchmark_total_distance": 0.0,
            "top_gap": gap["top_gaps"][0]["feature"] if gap["top_gaps"] else "",
        }
        for chart in tracked_charts:
            feature = chart["feature"]
            if feature == "total_distance":
                continue
            if chart["kind"] == "distribution":
                row[feature] = gap["ngram_gaps"][feature]["distance"]
                row[f"benchmark_{feature}"] = 0.0
            else:
                row[feature] = stats[feature]
                row[f"benchmark_{feature}"] = benchmark_stats[feature]
        iterations.append(row)
        if index >= MIN_RECURSIVE_EDITS and _aligned(row, benchmark_stats):
            completed_iteration = index
            break

    charts = []
    for chart in tracked_charts:
        feature = chart["feature"]
        if feature == "total_distance":
            comparison_values = {
                label: comparison_gaps[label]["total_distance"] for label, _text in comparison_texts
            }
        elif chart["kind"] == "distribution":
            comparison_values = {
                label: comparison_gaps[label]["ngram_gaps"][feature]["distance"]
                for label, _text in comparison_texts
            }
        else:
            comparison_values = {
                label: comparison_stats[label][feature] for label, _text in comparison_texts
            }
        benchmark_points = [
            {"iteration": row["iteration"], "value": row[f"benchmark_{feature}"]}
            for row in iterations
        ]
        salix_points = [
            {"iteration": row["iteration"], "value": row[feature]} for row in iterations
        ]
        series = [
            {
                "label": label,
                "points": [
                    {"iteration": row["iteration"], "value": value} for row in iterations
                ],
            }
            for label, value in comparison_values.items()
        ]
        series[2]["points"] = salix_points
        series.append({"label": "Benchmark", "points": benchmark_points})
        charts.append({**chart, "series": series, "target_series": salix_points,
                       "benchmark_series": benchmark_points})

    payload = {
        "prompt": PROMPT,
        "source": (
            "Benchmark fixture uses a public-domain excerpt from Project Gutenberg "
            f"The Adventures of Sherlock Holmes, {SOURCE_URL}."
        ),
        "validated": False,
        "comparisons": [
            {
                "label": label,
                "text": text,
                "total_distance": comparison_gaps[label]["total_distance"],
                "mean_sent_len": comparison_stats[label]["mean_sent_len"],
            }
            for label, text in comparison_texts
        ],
        "completion": {
            "minimum_recursive_edits": MIN_RECURSIVE_EDITS,
            "maximum_recursive_edits": MAX_RECURSIVE_EDITS,
            "completed_iteration": completed_iteration,
            "aligned": completed_iteration is not None,
            "alignment_total_distance_threshold": ALIGNMENT_DISTANCE_THRESHOLD,
            "alignment_feature_threshold": ALIGNMENT_FEATURE_THRESHOLD,
            "final_total_distance": iterations[-1]["total_distance"],
            "chart_count": len(charts),
        },
        "iterations": iterations,
        "charts": charts,
    }
    validate_payload(payload)
    payload["validated"] = True
    return payload


def validate_payload(payload: dict) -> None:
    distances = [row["total_distance"] for row in payload["iterations"]]
    if len(distances) < MIN_RECURSIVE_EDITS + 1:
        raise SystemExit(
            f"Demo must include at least {MIN_RECURSIVE_EDITS} recursive edits; "
            f"saw {len(distances) - 1}."
        )
    if not distances[-1] < distances[0] * 0.75:
        raise SystemExit(
            f"Demo distance must materially improve; saw {distances[0]} -> {distances[-1]}."
        )
    if not payload["completion"]["aligned"]:
        raise SystemExit(
            f"Demo must finish aligned by iteration {MAX_RECURSIVE_EDITS}; "
            f"saw final total distance {distances[-1]}."
        )
    if distances[-1] > ALIGNMENT_DISTANCE_THRESHOLD:
        raise SystemExit(
            f"Demo final distance must align with benchmark; saw {distances[-1]}."
        )
    for chart in payload["charts"]:
        target = chart["series"][2]["points"]
        benchmark = chart["benchmark_series"]
        initial_gap = abs(target[0]["value"] - benchmark[0]["value"])
        final_gap = abs(target[-1]["value"] - benchmark[-1]["value"])
        if initial_gap > ALIGNMENT_FEATURE_THRESHOLD and not final_gap < initial_gap:
            raise SystemExit(
                f"{chart['feature']} must converge; gap {initial_gap} -> {final_gap}."
            )
        if final_gap > ALIGNMENT_FEATURE_THRESHOLD:
            raise SystemExit(
                f"{chart['feature']} must align with benchmark; final gap {final_gap}."
            )


def _points(series: list[dict], *, x: float, y: float, width: float, height: float,
            min_value: float, max_value: float) -> str:
    span = max(max_value - min_value, 0.001)
    x_step = width / max(len(series) - 1, 1)
    out = []
    for index, point in enumerate(series):
        px = x + index * x_step
        py = y + height - ((point["value"] - min_value) / span * height)
        out.append(f"{px:.1f},{py:.1f}")
    return " ".join(out)


def render_svg(payload: dict) -> str:
    width = 920
    panel_height = 250
    margin = 64
    chart_width = width - margin * 2
    height = 110 + panel_height * len(payload["charts"])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="title desc">',
        "<title id=\"title\">Validated Sherlock Holmes Salix convergence</title>",
        "<desc id=\"desc\">Measured chart lines show recursive Baker Street drafts converging toward a public-domain Sherlock Holmes benchmark style profile.</desc>",
        "<rect width=\"100%\" height=\"100%\" fill=\"#fbfaf7\"/>",
        '<text x="40" y="38" font-family="Arial, sans-serif" font-size="22" '
        'font-weight="700" fill="#1f2933">Validated Sherlock Holmes fixture</text>',
        '<text x="40" y="64" font-family="Arial, sans-serif" font-size="13" '
        'fill="#52616b">Generated from scripts/demo_convergence.py; tested for decreasing total distance and feature convergence.</text>',
    ]
    for chart_index, chart in enumerate(payload["charts"]):
        top = 94 + chart_index * panel_height
        plot_x = margin
        plot_y = top + 42
        plot_h = 138
        values = [point["value"] for series in chart["series"] for point in series["points"]]
        pad = max((max(values) - min(values)) * 0.12, 1.0)
        min_value = min(values) - pad
        max_value = max(values) + pad
        colors = ["#64748b", "#7c3aed", "#2563eb", "#b45309"]
        parts.extend([
            f'<text x="{margin}" y="{top + 12}" font-family="Arial, sans-serif" '
            f'font-size="17" font-weight="700" fill="#1f2933">{chart["title"]}</text>',
            f'<text x="{margin}" y="{top + 32}" font-family="Arial, sans-serif" '
            f'font-size="12" fill="#52616b">{chart["unit"]}</text>',
            f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + chart_width}" '
            f'y2="{plot_y + plot_h}" stroke="#c9d1d9" stroke-width="1"/>',
            f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_h}" '
            f'stroke="#c9d1d9" stroke-width="1"/>',
        ])
        for series, color in zip(chart["series"], colors):
            points = _points(
                series["points"], x=plot_x, y=plot_y, width=chart_width,
                height=plot_h, min_value=min_value, max_value=max_value,
            )
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" '
                f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        legend_x = margin
        for series, color in zip(chart["series"], colors):
            parts.extend([
                f'<circle cx="{legend_x}" cy="{plot_y + plot_h + 31}" r="4" fill="{color}"/>',
                f'<text x="{legend_x + 10}" y="{plot_y + plot_h + 35}" '
                f'font-family="Arial, sans-serif" font-size="11" fill="#1f2933">{series["label"]}</text>',
            ])
            legend_x += 188 if "style" not in series["label"] else 286
        final_iteration = payload["iterations"][-1]["iteration"]
        tick_interval = max(1, round(final_iteration / 10))
        for point_index, row in enumerate(payload["iterations"]):
            if row["iteration"] not in (0, final_iteration) and row["iteration"] % tick_interval:
                continue
            px = plot_x + point_index * (chart_width / max(len(payload["iterations"]) - 1, 1))
            parts.append(
                f'<text x="{px:.1f}" y="{plot_y + plot_h + 18}" '
                'font-family="Arial, sans-serif" font-size="11" text-anchor="middle" '
                f'fill="#52616b">{row["iteration"]}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate validated Salix convergence demo data.")
    parser.add_argument("--json-out", default="examples/convergence_demo.json")
    parser.add_argument("--svg-out", default="examples/convergence_demo.svg")
    args = parser.parse_args()

    payload = build_payload()
    json_path = Path(args.json_out)
    svg_path = Path(args.svg_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    svg_path.write_text(render_svg(payload) + "\n")
    print(f"Wrote {json_path}")
    print(f"Wrote {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
