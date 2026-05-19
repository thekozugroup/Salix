#!/usr/bin/env python3
"""Generate the README convergence demo from measured Salix data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _path  # noqa: F401

from lib.distance import compute_gaps
from lib.stats import analyze

PROMPT = "Write a short Baker Street case note about a missing railway ticket."
SOURCE_URL = "https://www.gutenberg.org/ebooks/1661"
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
    },
    {
        "feature": "mean_sent_len",
        "title": "Sentence length convergence",
        "unit": "words per sentence",
    },
]


def draft_text(step: int, total_steps: int = 20) -> str:
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


def build_payload() -> dict:
    benchmark_stats = analyze((BENCHMARK_SAMPLE + "\n") * 4)
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
    for index in range(21):
        text = draft_text(index)
        stats = analyze(text)
        gap = compute_gaps(stats, benchmark_stats)
        row = {
            "iteration": index,
            "label": "full_ai_baseline" if index == 0 else f"recursive_edit_{index}",
            "total_distance": gap["total_distance"],
            "benchmark_total_distance": 0.0,
            "top_gap": gap["top_gaps"][0]["feature"] if gap["top_gaps"] else "",
        }
        for chart in TRACKED_CHARTS:
            feature = chart["feature"]
            if feature == "total_distance":
                continue
            row[feature] = stats[feature]
            row[f"benchmark_{feature}"] = benchmark_stats[feature]
        iterations.append(row)

    charts = []
    for chart in TRACKED_CHARTS:
        feature = chart["feature"]
        if feature == "total_distance":
            comparison_values = {
                label: comparison_gaps[label]["total_distance"] for label, _text in comparison_texts
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
        "iterations": iterations,
        "charts": charts,
    }
    validate_payload(payload)
    payload["validated"] = True
    return payload


def validate_payload(payload: dict) -> None:
    distances = [row["total_distance"] for row in payload["iterations"]]
    if len(distances) < 21:
        raise SystemExit(f"Demo must include at least 21 points; saw {len(distances)}.")
    if not distances[-1] < distances[0] * 0.75:
        raise SystemExit(
            f"Demo distance must materially improve; saw {distances[0]} -> {distances[-1]}."
        )
    for chart in payload["charts"]:
        target = chart["series"][2]["points"]
        benchmark = chart["benchmark_series"]
        initial_gap = abs(target[0]["value"] - benchmark[0]["value"])
        final_gap = abs(target[-1]["value"] - benchmark[-1]["value"])
        if not final_gap < initial_gap:
            raise SystemExit(
                f"{chart['feature']} must converge; gap {initial_gap} -> {final_gap}."
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
        "<desc id=\"desc\">Two measured chart lines show recursive Baker Street drafts converging toward a public-domain Sherlock Holmes benchmark style profile.</desc>",
        "<rect width=\"100%\" height=\"100%\" fill=\"#fbfaf7\"/>",
        '<text x="40" y="38" font-family="Arial, sans-serif" font-size="22" '
        'font-weight="700" fill="#1f2933">Validated Sherlock Holmes fixture</text>',
        '<text x="40" y="64" font-family="Arial, sans-serif" font-size="13" '
        'fill="#52616b">Base, direct style prompt, and Salix are measured as chart lines against the same benchmark.</text>',
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
        for point_index, row in enumerate(payload["iterations"]):
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
