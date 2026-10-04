#!/usr/bin/env python3
"""Generate a deterministic metric fixture, not evidence of AI/Salix convergence.

Snapshots depend on their index, not previous drafts or gap-driven edits. They
progressively copy the benchmark and end with the exact repeated excerpt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html import escape
from importlib.metadata import version
from pathlib import Path

import _path  # noqa: F401

from lib import stats as stats_module
from lib.distance import SKIP_FEATURES, compute_gaps
from lib.stats import analyze, split_sentences

PROMPT = "Write a short Baker Street case note about a missing railway ticket."
SOURCE_URL = "https://www.gutenberg.org/ebooks/1661"
SOURCE_DESCRIPTION = (
    "Copy-based metric fixture uses a public-domain excerpt from Project Gutenberg "
    f"The Adventures of Sherlock Holmes, {SOURCE_URL}."
)
BENCHMARK_RECIPE = "((excerpt_text + '\\n') * repeat_count).strip()"
FIXTURE_STEPS = 50
BENCHMARK_REPEAT_COUNT = 4
ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_TYPE = "deterministic_metric_fixture"
CLAIMS = {
    "ai_generation": False,
    "salix_recursive_edits": False,
    "ai_or_salix_convergence": False,
}
LIMITATIONS = [
    "Snapshots are deterministic index-based interpolation and benchmark copying, not recursive edits.",
    "The final snapshot is the exact benchmark text; a zero distance is a copy-based sanity check.",
    "Comparison texts are hardcoded illustrations, not observed model or Salix outputs.",
    "No model, provider, prompt execution, or Salix rewrite run is recorded.",
    "The benchmark repeats one excerpt four times; it is not an independent multi-document corpus.",
    "Distances do not test originality, task completion, meaning preservation, or writing quality.",
    "Optional spaCy availability changes POS/formality metrics; unavailable POS distances are not matches.",
    "Optional pyphen availability changes syllable/readability metrics; the fallback is a coarse heuristic.",
]
OVERVIEW_CHART_FEATURES = {
    "total_distance",
    "mean_sent_len",
    "mtld",
    "comma_per_sentence",
    "formality_f_score",
    "fw_the_per1k",
    "mfw_top150",
}
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
SALIX_INSPIRED_EXAMPLE = (
    "To Sherlock Holmes the missing railway ticket was not a trifle, but a small fact "
    "misplaced among larger ones. I have seldom seen him regard so slight a paper with "
    "such cold attention, for in his eyes the little oblong of pasteboard eclipsed the "
    "whole confusion of the case."
)

COMPARISON_FIXTURES = [
    ("base_example", "Base example (static)", "Base prompt only", BASE_PROMPT_OUTPUT),
    ("style_example", "Style example (static)",
     'Prompt plus "write in the style of Sherlock Holmes"', STYLE_PROMPT_OUTPUT),
    ("salix_inspired_example", "Salix-inspired (static)",
     "Base prompt plus Salix", SALIX_INSPIRED_EXAMPLE),
]
SERIES = [
    {"id": fixture_id, "label": label, "source": "comparison"}
    for fixture_id, label, _condition, _text in COMPARISON_FIXTURES
] + [
    {"id": "copy_fixture", "label": "Copy fixture (deterministic)", "source": "iterations"},
    {"id": "benchmark", "label": "Benchmark (4x excerpt)", "source": "benchmark"},
]

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
        "title": "Overall fixture distance",
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
    title_overrides = {
        "ttr": "TTR",
        "mtld": "MTLD",
        "yule_k": "Yule's K",
        "honore_r": "Honore's R",
        "simpson_d": "Simpson's D",
        "mean_word_len": "Mean word length",
        "mean_sent_len": "Sentence length",
        "stdev_sent_len": "Sentence length variation",
        "comma_per_sentence": "Comma cadence",
        "flesch_kincaid_grade": "Flesch-Kincaid grade",
        "gunning_fog": "Gunning Fog",
        "ari": "ARI",
        "formality_f_score": "Formality F-score",
    }
    if feature in title_overrides:
        return title_overrides[feature]
    if feature.startswith("fw_") and feature.endswith("_per1k"):
        word = feature.removeprefix("fw_").removesuffix("_per1k")
        return f'Function word "{word}"'
    if feature.startswith("punct_") and feature.endswith("_per1k"):
        mark = feature.removeprefix("punct_").removesuffix("_per1k").replace("_", " ")
        return f"Punctuation {mark}"
    return feature.replace("_per1k", "").replace("_", " ").title()


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
            "availability": "measured" if benchmark_stats[feature] else "unavailable",
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


def benchmark_text() -> str:
    return ((BENCHMARK_SAMPLE + "\n") * BENCHMARK_REPEAT_COUNT).strip()


def draft_text(step: int, total_steps: int = FIXTURE_STEPS) -> str:
    """Index-based copy fixture; no model calls, feedback, or previous draft."""
    if total_steps <= 0 or not 0 <= step <= total_steps:
        raise ValueError("Fixture step must be between zero and a positive total_steps.")
    alpha = step / total_steps
    if alpha >= 1.0:
        return benchmark_text()

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


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _runtime_provenance() -> dict:
    nlp = stats_module._get_spacy_nlp()
    pos_backend = {"kind": "heuristic_formality_empty_pos_ngrams"}
    if nlp is not None:
        pos_backend = {
            "kind": "spacy",
            "package_version": version("spacy"),
            "model_name": nlp.meta.get("name"),
            "model_version": nlp.meta.get("version"),
            "pipeline": list(nlp.pipe_names),
        }
    syllable_backend = {"kind": "vowel_group_heuristic"}
    if stats_module._get_pyphen() is not None:
        syllable_backend = {"kind": "pyphen", "package_version": version("pyphen"), "language": "en_US"}
    return {
        "python_version": sys.version.split()[0], "pos_backend": pos_backend,
        "syllable_backend": syllable_backend,
    }


def _provenance() -> dict:
    return {
        "hash_algorithm": "sha256",
        "text_encoding": "utf-8",
        "text_hash_scope": "exact stored text, including whitespace; no normalization",
        "generator": "scripts/demo_convergence.py",
        "source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "scripts/demo_convergence.py", "lib/stats.py", "lib/distance.py",
                "lib/function_words.py", "lib/tone.py",
            )
        },
        "runtime": _runtime_provenance(),
        "method": "Index-based sentence/token interpolation toward a benchmark copy; no feedback loop.",
    }


def _measure(text: str, benchmark_stats: dict, charts: list[dict]) -> dict:
    stats = analyze(text)
    gap = compute_gaps(stats, benchmark_stats)
    values = {}
    for chart in charts:
        feature = chart["feature"]
        if chart["kind"] == "distance":
            values[feature] = gap["total_distance"]
        elif chart["kind"] == "distribution":
            values[feature] = gap["ngram_gaps"][feature]["distance"]
        else:
            values[feature] = stats[feature]
    return {
        "values": values,
        "counts": {key: stats[key] for key in ("word_count", "sentence_count", "paragraph_count")},
    }


def build_payload() -> dict:
    benchmark = benchmark_text()
    benchmark_stats = analyze(benchmark)
    tracked_charts = _benchmark_feature_charts(benchmark_stats)
    iterations = []
    for index in range(FIXTURE_STEPS + 1):
        text = draft_text(index)
        iterations.append({
            "iteration": index,
            "label": f"copy_fixture_step_{index:02d}",
            "text": text,
            "sha256": _sha256(text),
            **_measure(text, benchmark_stats, tracked_charts),
        })

    payload = {
        "schema_version": 2,
        "evidence_type": EVIDENCE_TYPE,
        "claims": dict(CLAIMS),
        "limitations": list(LIMITATIONS),
        "prompt": PROMPT,
        "source": SOURCE_DESCRIPTION,
        "provenance": _provenance(),
        "benchmark": {
            "excerpt_text": BENCHMARK_SAMPLE,
            "excerpt_sha256": _sha256(BENCHMARK_SAMPLE),
            "repeat_count": BENCHMARK_REPEAT_COUNT,
            "recipe": BENCHMARK_RECIPE,
            "text": benchmark,
            "sha256": _sha256(benchmark),
            "source_url": SOURCE_URL,
            **_measure(benchmark, benchmark_stats, tracked_charts),
        },
        "comparisons": [
            {
                "id": fixture_id,
                "label": label,
                "illustrated_condition": condition,
                "origin": "hardcoded_illustrative_text_not_observed_output",
                "text": text,
                "sha256": _sha256(text),
                **_measure(text, benchmark_stats, tracked_charts),
            }
            for fixture_id, label, condition, text in COMPARISON_FIXTURES
        ],
        "completion": {
            "scope": "fixture_generation_only",
            "status": "fixture_generated",
            "fixture_steps": FIXTURE_STEPS,
            "snapshot_count": len(iterations),
            "final_step": iterations[-1]["iteration"],
            "final_text_equals_benchmark": iterations[-1]["text"] == benchmark,
            "final_total_distance": iterations[-1]["values"]["total_distance"],
            "ai_or_salix_convergence_proven": False,
            "reason": "Final snapshot is a verbatim benchmark copy, not a successful rewrite.",
            "chart_count": len(tracked_charts),
            "overview_chart_count": len([
                chart for chart in tracked_charts if chart["feature"] in OVERVIEW_CHART_FEATURES
            ]),
        },
        "iterations": iterations,
        "series": [dict(series) for series in SERIES],
        "charts": tracked_charts,
        "validation": {"scope": "provenance_and_metric_consistency_only", "passed": False},
    }
    validate_payload(payload)
    payload["validation"]["passed"] = True
    return payload


def validate_payload(payload: dict) -> None:
    """Validate this fixture's provenance/measurements, never rewrite success."""
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    require(payload["schema_version"] == 2, "Unsupported fixture schema.")
    require(payload["evidence_type"] == EVIDENCE_TYPE, "Fixture evidence type is mislabeled.")
    require(set(payload["claims"]) == set(CLAIMS) and all(value is False for value in payload["claims"].values()),
            "Fixture cannot claim AI/Salix generation or convergence.")
    require("validated" not in payload and "aligned" not in payload["completion"],
            "Legacy validation/alignment flags cannot imply convergence.")
    require(payload["limitations"] == LIMITATIONS, "Fixture limitations must remain explicit.")
    require(payload["provenance"] == _provenance(), "Source/runtime provenance does not match.")
    require(payload["prompt"] == PROMPT, "Illustrative prompt changed.")
    require(payload["source"] == SOURCE_DESCRIPTION, "Source must describe a copy-based metric fixture.")
    require(payload["series"] == SERIES, "Series must distinguish static examples from copying.")
    require(payload["validation"]["scope"] == "provenance_and_metric_consistency_only",
            "Validation must not imply AI/Salix convergence.")
    require(type(payload["validation"]["passed"]) is bool, "Validation status must be boolean.")
    benchmark = payload["benchmark"]
    require(benchmark["excerpt_text"] == BENCHMARK_SAMPLE, "Benchmark excerpt changed.")
    require(benchmark["excerpt_sha256"] == _sha256(benchmark["excerpt_text"]),
            "Benchmark excerpt hash mismatch.")
    require(benchmark["repeat_count"] == BENCHMARK_REPEAT_COUNT, "Benchmark repetition changed.")
    require(benchmark["recipe"] == BENCHMARK_RECIPE, "Benchmark recipe description changed.")
    require(benchmark["text"] == benchmark_text(), "Benchmark copy recipe mismatch.")
    require(benchmark["source_url"] == SOURCE_URL, "Benchmark attribution mismatch.")
    benchmark_stats = analyze(benchmark["text"])
    charts = _benchmark_feature_charts(benchmark_stats)
    require(payload["charts"] == charts, "Chart metadata or availability mismatch.")

    def check_measurement(record: dict) -> None:
        require(record["sha256"] == _sha256(record["text"]), "Text SHA-256 mismatch.")
        measured = _measure(record["text"], benchmark_stats, charts)
        require(record["values"] == measured["values"], "Metrics do not match recorded text.")
        require(record["counts"] == measured["counts"], "Counts do not match recorded text.")

    check_measurement(benchmark)
    require(len(payload["comparisons"]) == len(COMPARISON_FIXTURES), "Missing static comparisons.")
    for record, (fixture_id, label, condition, text) in zip(payload["comparisons"], COMPARISON_FIXTURES):
        require((record["id"], record["label"], record["illustrated_condition"], record["text"])
                == (fixture_id, label, condition, text), "Static comparison provenance changed.")
        require(record["origin"] == "hardcoded_illustrative_text_not_observed_output",
                "Static comparison cannot claim an observed output.")
        check_measurement(record)

    rows = payload["iterations"]
    require(len(rows) == FIXTURE_STEPS + 1, "Fixture must contain steps 0 through 50.")
    for index, row in enumerate(rows):
        require(row["iteration"] == index, "Fixture steps must be contiguous and ordered.")
        require(row["label"] == f"copy_fixture_step_{index:02d}", "Snapshot is not labeled as copying.")
        require(row["text"] == draft_text(index), "Snapshot does not match deterministic copy recipe.")
        check_measurement(row)

    completion = payload["completion"]
    require(completion["scope"] == "fixture_generation_only" and completion["status"] == "fixture_generated",
            "Completion means fixture generation only.")
    require(completion["ai_or_salix_convergence_proven"] is False,
            "Copying cannot prove AI/Salix convergence.")
    require(completion["reason"] == "Final snapshot is a verbatim benchmark copy, not a successful rewrite.",
            "Completion must disclose copying, not rewrite success.")
    require(completion["fixture_steps"] == FIXTURE_STEPS and completion["final_step"] == FIXTURE_STEPS
            and completion["snapshot_count"] == len(rows), "Fixture completion count mismatch.")
    require(completion["final_text_equals_benchmark"] is True and rows[-1]["text"] == benchmark["text"],
            "Final fixture must disclose its exact benchmark copy.")
    require(completion["final_total_distance"] == rows[-1]["values"]["total_distance"],
            "Final distance does not match recorded metrics.")
    require(completion["chart_count"] == len(charts) and completion["overview_chart_count"]
            == len([chart for chart in charts if chart["feature"] in OVERVIEW_CHART_FEATURES]),
            "Chart count mismatch.")


def chart_series(payload: dict, chart: dict) -> list[dict]:
    """Expand shared measurements for rendering, without duplicating JSON points."""
    feature = chart["feature"]
    comparisons = {record["id"]: record for record in payload["comparisons"]}
    series = []
    for spec in payload["series"]:
        if spec["source"] == "iterations":
            values = [row["values"][feature] for row in payload["iterations"]]
        else:
            record = payload["benchmark"] if spec["source"] == "benchmark" else comparisons[spec["id"]]
            values = [record["values"][feature]] * len(payload["iterations"])
        series.append({
            "id": spec["id"], "label": spec["label"],
            "points": [
                {"iteration": row["iteration"], "value": value}
                for row, value in zip(payload["iterations"], values)
            ],
        })
    return series


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


def render_svg(payload: dict, charts: list[dict] | None = None) -> str:
    charts = charts if charts is not None else payload["charts"]
    width = 920
    panel_height = 300
    margin = 64
    chart_width = width - margin * 2
    height = 140 + panel_height * len(charts)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="title desc">',
        '<title id="title">Deterministic metric fixture: benchmark-copy sanity check</title>',
        '<desc id="desc">50 deterministic copy steps, three static illustrative texts, and a repeated Sherlock Holmes benchmark. Values are measured from stored texts, not AI/Salix recursive edits or proof of convergence.</desc>',
        "<rect width=\"100%\" height=\"100%\" fill=\"#fbfaf7\"/>",
        '<text x="40" y="38" font-family="Arial, sans-serif" font-size="22" '
        'font-weight="700" fill="#1f2933">Deterministic metric fixture: benchmark-copy sanity check</text>',
        '<text x="40" y="64" font-family="Arial, sans-serif" font-size="13" '
        'fill="#52616b">50 copy steps; static illustrative comparisons; not proof of AI or Salix convergence.</text>',
        '<text x="40" y="86" font-family="Arial, sans-serif" font-size="12" '
        'fill="#52616b">Exact texts, SHA-256 hashes, values, and source/runtime provenance: convergence_demo.json.</text>',
    ]
    for chart_index, chart in enumerate(charts):
        top = 120 + chart_index * panel_height
        plot_x = margin
        plot_y = top + 42
        plot_h = 138
        series_data = chart_series(payload, chart)
        values = [point["value"] for series in series_data for point in series["points"]]
        pad = max((max(values) - min(values)) * 0.12, abs(max(values)) * 0.03, 0.01)
        min_value = max(0.0, min(values) - pad) if min(values) >= 0 else min(values) - pad
        max_value = max(values) + pad
        colors = ["#64748b", "#7c3aed", "#0f766e", "#2563eb", "#b45309"]
        unavailable = chart.get("availability") == "unavailable"
        unit = (
            "Unavailable POS n-grams: zeros are placeholders, not evidence of a match."
            if unavailable else chart["unit"]
        )
        parts.extend([
            f'<text x="{margin}" y="{top + 12}" font-family="Arial, sans-serif" '
            f'font-size="17" font-weight="700" fill="#1f2933">{escape(chart["title"])}</text>',
            f'<text x="{margin}" y="{top + 32}" font-family="Arial, sans-serif" '
            f'font-size="12" fill="#52616b">{escape(unit)}</text>',
            f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + chart_width}" '
            f'y2="{plot_y + plot_h}" stroke="#c9d1d9" stroke-width="1"/>',
            f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_h}" '
            f'stroke="#c9d1d9" stroke-width="1"/>',
        ])
        for tick in range(3):
            value = min_value + (max_value - min_value) * tick / 2
            py = plot_y + plot_h - plot_h * tick / 2
            parts.append(
                f'<text x="{plot_x - 8}" y="{py + 4}" font-family="Arial, sans-serif" '
                f'font-size="10" text-anchor="end" fill="#52616b">{value:.4g}</text>'
            )
        for series, color in zip(series_data, colors):
            points = _points(
                series["points"], x=plot_x, y=plot_y, width=chart_width,
                height=plot_h, min_value=min_value, max_value=max_value,
            )
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" '
                f'data-series-id="{series["id"]}" data-available="{str(not unavailable).lower()}" '
                f'stroke-dasharray="{"4 4" if unavailable else "none"}" '
                f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                f'<title>{escape(series["label"])}: start {series["points"][0]["value"]}, '
                f'end {series["points"][-1]["value"]}</title></polyline>'
            )
        for index, (series, color) in enumerate(zip(series_data, colors)):
            legend_x = margin + (index % 3) * 270
            legend_y = plot_y + plot_h + 38 + (index // 3) * 22
            parts.extend([
                f'<circle cx="{legend_x}" cy="{legend_y - 4}" r="4" fill="{color}"/>',
                f'<text x="{legend_x + 10}" y="{legend_y}" '
                f'font-family="Arial, sans-serif" font-size="11" fill="#1f2933">{escape(series["label"])}</text>',
            ])
        parts.append(
            f'<text x="{plot_x + chart_width / 2}" y="{plot_y + plot_h + 89}" '
            'font-family="Arial, sans-serif" font-size="11" text-anchor="middle" '
            'fill="#52616b">Deterministic copy step (not a recursive edit)</text>'
        )
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


def _chart_filename(index: int, chart: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", chart["feature"].lower()).strip("-")
    return f"{index:03d}-{slug}.svg"


def render_charts_index(payload: dict, files: list[tuple[str, dict]]) -> str:
    lines = [
        "# Deterministic metric fixture charts",
        "",
        "Generated by `scripts/demo_convergence.py` from `examples/convergence_demo.json`.",
        "",
        "These graphs are a copy-based sanity check, not proof of AI or Salix convergence.",
        "Steps 0-50 progressively copy the benchmark; step 50 is the exact repeated excerpt.",
        "All three comparison lines are static hardcoded illustrations, not observed outputs.",
        "Completion means fixture generation only. Validation checks provenance and measured values.",
        "",
        "Exact text and SHA-256 hashes are stored once per snapshot/comparison in the JSON.",
        "Shared benchmark values and series metadata avoid duplicating chart point arrays.",
        "Optional POS metrics are labeled unavailable when no spaCy model is loaded; zeros are not matches.",
        "",
        "| Chart | Variable | Type |",
        "| --- | --- | --- |",
    ]
    for filename, chart in files:
        lines.append(f"| [{chart['title']}]({filename}) | `{chart['feature']}` | {chart['kind']} |")
    return "\n".join(lines) + "\n"


def write_chart_folder(payload: dict, charts_dir: Path) -> None:
    charts_dir.mkdir(parents=True, exist_ok=True)
    # Only replace this run's named outputs; unrelated and stale SVGs are preserved.
    files = []
    for index, chart in enumerate(payload["charts"], start=1):
        filename = _chart_filename(index, chart)
        (charts_dir / filename).write_text(render_svg(payload, [chart]) + "\n", encoding="utf-8")
        files.append((filename, chart))
    (charts_dir / "README.md").write_text(render_charts_index(payload, files), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic metric fixture and copy-based sanity-check charts, not AI/Salix convergence evidence.")
    parser.add_argument("--json-out", default="examples/convergence_demo.json")
    parser.add_argument("--svg-out", default="examples/convergence_demo.svg")
    parser.add_argument("--charts-dir", default="examples/convergence_charts")
    args = parser.parse_args()

    payload = build_payload()
    json_path = Path(args.json_out)
    svg_path = Path(args.svg_out)
    charts_dir = Path(args.charts_dir)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    overview_charts = [
        chart for chart in payload["charts"] if chart["feature"] in OVERVIEW_CHART_FEATURES
    ]
    svg_path.write_text(render_svg(payload, overview_charts) + "\n", encoding="utf-8")
    write_chart_folder(payload, charts_dir)
    print(f"Wrote {json_path}")
    print(f"Wrote {svg_path}")
    print(f"Wrote {charts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
