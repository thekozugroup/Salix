#!/usr/bin/env python3
"""Render recorded rewrite measurements; never manufacture missing observations."""

from __future__ import annotations

import argparse
import math
import re
from html import escape
from pathlib import Path

import _path  # noqa: F401
from demo_convergence import _benchmark_feature_charts
from live_convergence import validate_payload

from lib.distance import compute_gaps
from lib.io_utils import load_json

WIDTH = 920
PANEL_HEIGHT = 300
COLORS = {
    "candidate": "#8b949e", "retained": "#2563eb", "base": "#d55e00",
    "style": "#7c3aed", "benchmark": "#00856a",
}


def render_svg(charts: list[dict], attempts: int, subtitle: str) -> str:
    if type(attempts) is not int or attempts < 0:
        raise ValueError("Attempt count must be a nonnegative integer.")
    height = 120 + PANEL_HEIGHT * len(charts)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Sherlock Holmes rewrite experiment</title>',
        f'<desc id="desc">{escape(subtitle)}. Candidate drafts include rejected attempts. '
        'Retained drafts are selected using training measurements, not held-out results. '
        'Lower distance is not a percentage voice match.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<g font-family="Arial, sans-serif" fill="#20252b">',
        '<text x="64" y="38" font-size="22" font-weight="700">Sherlock Holmes rewrite experiment</text>',
        f'<text x="64" y="62" font-size="12" fill="#53616f">{escape(subtitle)}</text>',
        '<text x="64" y="82" font-size="12" fill="#53616f">'
        'Recorded outputs and measured scores; no benchmark copying or forced alignment.</text>',
    ]
    x, plot_width, plot_height = 64, 792, 138
    for index, chart in enumerate(charts):
        top = 116 + index * PANEL_HEIGHT
        y = top + 42
        parts.extend([
            f'<text x="{x}" y="{top + 12}" font-size="17" font-weight="700">{escape(chart["title"])}</text>',
            f'<text x="{x}" y="{top + 32}" font-size="12" fill="#53616f">{escape(chart["unit"])}</text>',
        ])
        if chart.get("availability") == "unavailable":
            parts.append(f'<text x="{x}" y="{y + 60}" font-size="13" fill="#53616f">'
                         'Not measured: requires a spaCy English model. No match is implied.</text>')
            continue
        series = chart["series"]
        values = [value for item in series for value in item["values"] if value is not None]
        if not values or not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            raise ValueError("Charts require finite recorded measurements.")
        if any(len(item["values"]) != attempts + 1 for item in series):
            raise ValueError("Each line must include all attempted iterations.")
        padding = max((max(values) - min(values)) * 0.1, abs(max(values)) * 0.02, 0.01)
        low = max(0, min(values) - padding) if min(values) >= 0 else min(values) - padding
        high = max(values) + padding
        for tick in range(4):
            value = low + (high - low) * tick / 3
            py = y + plot_height - plot_height * tick / 3
            parts.extend([
                f'<line x1="{x}" y1="{py:.2f}" x2="{x + plot_width}" y2="{py:.2f}" stroke="#e6e9ed"/>',
                f'<text x="{x - 8}" y="{py + 4:.2f}" font-size="10" text-anchor="end" fill="#53616f">{value:.4g}</text>',
            ])
        for item in series:
            segments, points = [], []
            for step, value in enumerate(item["values"]):
                if value is None:
                    if points:
                        segments.append(points)
                    points = []
                    continue
                points.append(f'{x + step * plot_width / max(attempts, 1):.2f},'
                              f'{y + plot_height - (value - low) * plot_height / (high - low):.2f}')
            if points:
                segments.append(points)
            color = COLORS[item["id"]]
            dash = "4 4" if item["id"] in {"base", "style", "benchmark"} else "none"
            weight = "1.25" if item["id"] == "candidate" else "2.3"
            for segment in segments:
                coordinates = " ".join(segment)
                parts.append(f'<polyline data-series-id="{item["id"]}" points="{coordinates}" '
                             f'fill="none" stroke="{color}" stroke-width="{weight}" '
                             f'stroke-dasharray="{dash}" stroke-linejoin="round">'
                             f'<title>{escape(item["label"])}: {item["values"][0]} to '
                             f'{item["values"][-1]}</title></polyline>')
                if len(segment) == 1:
                    cx, cy = segment[0].split(",")
                    parts.append(f'<circle cx="{cx}" cy="{cy}" r="2" fill="{color}"/>')
        ticks = sorted({0, attempts, *range(0, attempts + 1, max(1, math.ceil(attempts / 10)))})
        for step in ticks:
            px = x + step * plot_width / max(attempts, 1)
            parts.append(f'<text x="{px:.2f}" y="{y + plot_height + 18}" font-size="10" '
                         f'text-anchor="middle" fill="#53616f">{step}</text>')
        for line_index, item in enumerate(series):
            lx = x + (line_index % 3) * 270
            ly = y + plot_height + 38 + (line_index // 3) * 22
            parts.extend([
                f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 15}" y2="{ly - 4}" stroke="{COLORS[item["id"]]}" stroke-width="2"/>',
                f'<text x="{lx + 22}" y="{ly}" font-size="11">{escape(item["label"])}</text>',
            ])
        parts.append(f'<text x="{x + plot_width / 2}" y="{y + plot_height + 85}" '
                     'font-size="11" text-anchor="middle" fill="#53616f">Attempted rewrite</text>')
    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts) + "\n"


def write_charts(charts: list[dict], attempts: int, subtitle: str, out: Path, folder: Path) -> None:
    overview = {"total_distance", "heldout_distance", "mean_sent_len", "comma_per_sentence"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_svg([chart for chart in charts if chart["feature"] in overview], attempts, subtitle),
                   encoding="utf-8")
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["# Recorded Rewrite Charts", "", subtitle, "",
             "All lines are measured from recorded texts. Grey shows every candidate, including rejected drafts.",
             "Blue retains the best eligible training-score draft. Held-out results do not choose edits.",
             "Zero distance and universal writing fidelity are not claimed. Unavailable POS features are not matches.",
             "", "[Method and exact outputs](../live_convergence.json)", "",
             "| Measurement | Variable |", "| --- | --- |"]
    for index, chart in enumerate(charts, 1):
        slug = re.sub(r"[^a-z0-9]+", "-", chart["feature"].lower()).strip("-")
        filename = f"{index:03d}-{slug}.svg"
        (folder / filename).write_text(render_svg([chart], attempts, subtitle), encoding="utf-8")
        lines.append(f'| [{chart["title"]}]({filename}) | `{chart["feature"]}` |')
    (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="examples/live_convergence.json")
    parser.add_argument("--out", default="examples/live_convergence.svg")
    parser.add_argument("--charts-dir", default="examples/live_convergence_charts")
    args = parser.parse_args()
    payload = load_json(Path(args.input))
    charts, attempts, subtitle = prepare_charts(payload)
    write_charts(charts, attempts, subtitle, Path(args.out), Path(args.charts_dir))
    print(f"Wrote {args.out} and {args.charts_dir}")
    return 0


def prepare_charts(payload: dict) -> tuple[list[dict], int, str]:
    validate_payload(payload)
    calls, rows = payload["calls"], payload["iterations"]
    training = payload["benchmarks"]["training"]
    heldout = payload["benchmarks"]["heldout"]
    gaps = [compute_gaps(call["stats"], training) for call in calls]
    specifications = _benchmark_feature_charts(training)
    specifications[0] = {"feature": "total_distance", "title": "Distance to training profile",
                         "kind": "distance", "unit": "weighted Salix distance; lower is closer"}
    specifications.insert(1, {"feature": "heldout_distance", "title": "Distance to held-out profile",
                              "kind": "distance", "unit": "held-out scores do not rank edits; lower is closer"})

    def value(call_index: int | None, chart: dict) -> float | None:
        if call_index is None:
            return None
        feature = chart["feature"]
        if feature == "total_distance":
            return calls[call_index]["training_distance"]
        if feature == "heldout_distance":
            return calls[call_index]["heldout_distance"]
        if chart["kind"] == "distribution":
            return gaps[call_index]["ngram_gaps"][feature]["distance"]
        return calls[call_index]["stats"][feature]

    charts = []
    for chart in specifications:
        feature = chart["feature"]
        if chart["kind"] == "scalar":
            benchmark = training[feature]
        elif feature == "heldout_distance":
            benchmark = compute_gaps(heldout, heldout)["total_distance"]
        elif chart["kind"] == "distribution":
            benchmark = compute_gaps(training, training)["ngram_gaps"][feature]["distance"]
        else:
            benchmark = compute_gaps(training, training)["total_distance"]
        lines = [
            {"id": "candidate", "label": "Every candidate draft", "values": [value(row["candidate"], chart) for row in rows]},
            {"id": "base", "label": "Base prompt only", "values": [value(0, chart)] * len(rows)},
            {"id": "style", "label": "Base + explicit style prompt", "values": [value(1, chart)] * len(rows)},
            {"id": "benchmark", "label": "Author profile reference", "values": [benchmark] * len(rows)},
            {"id": "retained", "label": "Salix retained draft", "values": [value(row["retained"], chart) for row in rows]},
        ]
        charts.append({**chart, "series": lines})
    attempts = len(rows) - 1
    model = payload["runtime"]["requested_model"]
    subtitle = f"{attempts} recorded rewrite attempts; {model}; three training and three held-out passages."
    return charts, attempts, subtitle


if __name__ == "__main__":
    raise SystemExit(main())
