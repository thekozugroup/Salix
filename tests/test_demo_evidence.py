"""Independent evidence checks for the deterministic copy fixture, not a rewrite run."""

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import demo_convergence as demo  # noqa: E402

from lib import stats as stats_module  # noqa: E402
from lib.distance import compute_gaps  # noqa: E402
from lib.stats import analyze  # noqa: E402

SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def recorded_backends(payload):
    """Reproduce the recorded fallback even on machines with optional libraries."""
    recorded = payload["provenance"]["runtime"]
    current = demo._runtime_provenance()
    with ExitStack() as stack:
        if recorded["pos_backend"]["kind"] == "heuristic_formality_empty_pos_ngrams":
            stack.enter_context(patch("lib.stats._get_spacy_nlp", return_value=None))
        elif recorded["pos_backend"] != current["pos_backend"]:
            raise unittest.SkipTest("Recorded spaCy model/version is unavailable for artifact reproduction.")
        if recorded["syllable_backend"]["kind"] == "vowel_group_heuristic":
            stack.enter_context(patch("lib.stats._get_pyphen", return_value=None))
        elif recorded["syllable_backend"] != current["syllable_backend"]:
            raise unittest.SkipTest("Recorded pyphen version is unavailable for artifact reproduction.")
        stats_module.estimate_syllables.cache_clear()
        try:
            yield
        finally:
            stats_module.estimate_syllables.cache_clear()


class TestDemoEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = demo.build_payload()
        cls.checked = json.loads((ROOT / "examples/convergence_demo.json").read_text(encoding="utf-8"))

    def assert_independent_measurements(self, payload):
        """Remeasure saved text directly, without the demo's measurement helper."""
        benchmark_stats = analyze(payload["benchmark"]["text"])
        records = [payload["benchmark"], *payload["comparisons"], *payload["iterations"]]
        features = {chart["feature"] for chart in payload["charts"]}
        for record in records:
            with self.subTest(record=record.get("label", "benchmark")):
                self.assertEqual(record["sha256"], text_hash(record["text"]))
                stats = analyze(record["text"])
                gaps = compute_gaps(stats, benchmark_stats)
                self.assertEqual(set(record["values"]), features)
                for key in ("word_count", "sentence_count", "paragraph_count"):
                    self.assertEqual(record["counts"][key], stats[key])
                for chart in payload["charts"]:
                    feature = chart["feature"]
                    if feature == "total_distance":
                        expected = gaps["total_distance"]
                    elif chart["kind"] == "distribution":
                        expected = gaps["ngram_gaps"][feature]["distance"]
                    else:
                        expected = stats[feature]
                    value = record["values"][feature]
                    self.assertTrue(math.isfinite(value), feature)
                    self.assertEqual(value, expected, feature)

    def test_every_value_and_hash_comes_from_the_saved_text(self):
        self.assert_independent_measurements(self.payload)

    def test_checked_in_texts_and_values_are_independently_reproducible(self):
        checked = self.checked
        for path, digest in checked["provenance"]["source_sha256"].items():
            self.assertEqual(
                digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                f"Regenerate fixture artifacts: source changed at {path}.",
            )
        with recorded_backends(checked):
            self.assert_independent_measurements(checked)
            generated = demo.build_payload()
        # The recorded interpreter version is historical provenance, not a CI pin.
        expected = copy.deepcopy(checked)
        expected["provenance"]["runtime"]["python_version"] = sys.version.split()[0]
        self.assertEqual(expected, generated, "Regenerate fixture artifacts after source changes.")

    def test_provenance_hashes_cover_exact_text_and_metric_sources(self):
        payload = self.payload
        benchmark = payload["benchmark"]
        self.assertEqual(benchmark["excerpt_sha256"], text_hash(benchmark["excerpt_text"]))
        self.assertEqual(benchmark["repeat_count"], 4)
        self.assertEqual(benchmark["text"], ((benchmark["excerpt_text"] + "\n") * 4).strip())
        self.assertNotEqual(text_hash("a\nb"), text_hash("a b"))
        self.assertEqual(payload["provenance"]["text_encoding"], "utf-8")
        self.assertEqual(payload["provenance"]["hash_algorithm"], "sha256")
        source_hashes = payload["provenance"]["source_sha256"]
        self.assertEqual(set(source_hashes), {
            "scripts/demo_convergence.py", "lib/stats.py", "lib/distance.py",
            "lib/function_words.py", "lib/tone.py",
        })
        for path, digest in source_hashes.items():
            self.assertEqual(digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        runtime = payload["provenance"]["runtime"]
        self.assertEqual(runtime["python_version"], sys.version.split()[0])
        self.assertIn(runtime["pos_backend"]["kind"], {"spacy", "heuristic_formality_empty_pos_ngrams"})
        self.assertIn(runtime["syllable_backend"]["kind"], {"pyphen", "vowel_group_heuristic"})

    def test_zero_distance_is_only_a_benchmark_copy_sanity_check(self):
        payload = self.payload
        rows = payload["iterations"]
        self.assertEqual([row["iteration"] for row in rows], list(range(51)))
        self.assertEqual(rows[-1]["text"], payload["benchmark"]["text"])
        self.assertEqual(rows[-1]["sha256"], payload["benchmark"]["sha256"])
        self.assertEqual(rows[-1]["values"], payload["benchmark"]["values"])
        self.assertEqual(rows[-1]["values"]["total_distance"], 0.0)
        self.assertNotEqual(rows[0]["sha256"], rows[-1]["sha256"])
        self.assertGreater(rows[-1]["counts"]["word_count"], rows[-2]["counts"]["word_count"] * 3)
        self.assertNotIn("railway ticket", rows[-1]["text"])
        self.assertTrue(all(value is False for value in payload["claims"].values()))
        self.assertEqual(payload["evidence_type"], "deterministic_metric_fixture")
        self.assertEqual(payload["completion"]["scope"], "fixture_generation_only")
        self.assertIs(payload["completion"]["ai_or_salix_convergence_proven"], False)
        self.assertNotIn("aligned", payload["completion"])
        self.assertNotIn("completed_iteration", payload["completion"])
        self.assertNotIn("validated", payload)
        self.assertEqual(payload["validation"]["scope"], "provenance_and_metric_consistency_only")

    def test_static_comparisons_are_not_replaced_by_the_copy_path(self):
        payload = self.payload
        labels = [spec["label"] for spec in payload["series"]]
        self.assertEqual(labels, [
            "Base example (static)", "Style example (static)", "Salix-inspired (static)",
            "Copy fixture (deterministic)", "Benchmark (4x excerpt)",
        ])
        for comparison in payload["comparisons"]:
            self.assertEqual(comparison["origin"], "hardcoded_illustrative_text_not_observed_output")
            self.assertNotEqual(comparison["sha256"], payload["iterations"][-1]["sha256"])
        for chart in payload["charts"]:
            series = {spec["id"]: spec for spec in demo.chart_series(payload, chart)}
            feature = chart["feature"]
            for comparison in payload["comparisons"]:
                points = series[comparison["id"]]["points"]
                self.assertEqual(len(points), 51)
                self.assertEqual([point["value"] for point in points], [comparison["values"][feature]] * 51)
            self.assertEqual(
                [point["value"] for point in series["copy_fixture"]["points"]],
                [row["values"][feature] for row in payload["iterations"]],
            )
            self.assertEqual(
                [point["value"] for point in series["benchmark"]["points"]],
                [payload["benchmark"]["values"][feature]] * 51,
            )

    def test_json_stores_measurements_once_not_duplicated_point_arrays(self):
        payload = self.payload
        self.assertLess(len(json.dumps(payload, indent=2).encode("utf-8")), 350_000)
        self.assertTrue(all("series" not in chart for chart in payload["charts"]))
        self.assertTrue(all("benchmark_series" not in chart for chart in payload["charts"]))
        self.assertTrue(all("points" not in series for series in payload["series"]))
        self.assertTrue(all(not key.startswith("benchmark_") for row in payload["iterations"] for key in row))

    def test_unavailable_pos_zeros_are_not_reported_as_matches(self):
        payload = self.payload
        stats = analyze(payload["benchmark"]["text"])
        for chart in payload["charts"]:
            if chart["feature"] not in {"pos_bigrams", "pos_trigrams"}:
                continue
            unavailable = not stats[chart["feature"]]
            self.assertEqual(chart["availability"], "unavailable" if unavailable else "measured")
            svg = demo.render_svg(payload, [chart])
            if unavailable:
                self.assertIn("zeros are placeholders, not evidence of a match", svg)
                self.assertEqual(svg.count('data-available="false"'), 5)

    def test_rejects_unearned_ai_or_salix_claims(self):
        for claim in ("ai_generation", "salix_recursive_edits", "ai_or_salix_convergence"):
            for false_claim in (True, 0):
                with self.subTest(claim=claim, value=false_claim):
                    payload = copy.deepcopy(self.payload)
                    payload["claims"][claim] = false_claim
                    with self.assertRaisesRegex(ValueError, "cannot claim"):
                        demo.validate_payload(payload)

    def test_rejects_legacy_validated_alignment_flags(self):
        payload = copy.deepcopy(self.payload)
        payload["validated"] = True
        with self.assertRaisesRegex(ValueError, "Legacy"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["completion"]["aligned"] = True
        with self.assertRaisesRegex(ValueError, "Legacy"):
            demo.validate_payload(payload)

    def test_rejects_completion_as_proof_even_with_zero_distance(self):
        payload = copy.deepcopy(self.payload)
        payload["completion"]["ai_or_salix_convergence_proven"] = True
        with self.assertRaisesRegex(ValueError, "cannot prove"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["completion"]["scope"] = "recursive_rewrite_success"
        with self.assertRaisesRegex(ValueError, "fixture generation only"):
            demo.validate_payload(payload)

    def test_rejects_tampered_text_and_hash(self):
        payload = copy.deepcopy(self.payload)
        payload["comparisons"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        row = payload["iterations"][23]
        row["text"] += " Altered evidence."
        row["sha256"] = text_hash(row["text"])
        with self.assertRaisesRegex(ValueError, "copy recipe"):
            demo.validate_payload(payload)

    def test_rejects_fabricated_scalar_distribution_and_distance_values(self):
        for feature in ("mean_sent_len", "fw_bigrams", "total_distance"):
            with self.subTest(feature=feature):
                payload = copy.deepcopy(self.payload)
                payload["iterations"][10]["values"][feature] += 0.125
                with self.assertRaisesRegex(ValueError, "Metrics"):
                    demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["iterations"][0]["values"] = dict(payload["benchmark"]["values"])
        with self.assertRaisesRegex(ValueError, "Metrics"):
            demo.validate_payload(payload)

    def test_rejects_tampered_counts_benchmark_and_source_provenance(self):
        payload = copy.deepcopy(self.payload)
        payload["iterations"][1]["counts"]["word_count"] += 1
        with self.assertRaisesRegex(ValueError, "Counts"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["benchmark"]["values"]["mean_sent_len"] += 1
        with self.assertRaisesRegex(ValueError, "Metrics"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["benchmark"]["repeat_count"] = 1
        with self.assertRaisesRegex(ValueError, "repetition"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["provenance"]["source_sha256"]["lib/stats.py"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "provenance"):
            demo.validate_payload(payload)

    def test_rejects_mislabeled_series_or_observed_output_origin(self):
        payload = copy.deepcopy(self.payload)
        payload["series"][3]["label"] = "Base prompt plus Salix"
        with self.assertRaisesRegex(ValueError, "Series"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["comparisons"][2]["origin"] = "observed_salix_output"
        with self.assertRaisesRegex(ValueError, "observed output"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["iterations"][0]["label"] = "full_ai_baseline"
        with self.assertRaisesRegex(ValueError, "labeled as copying"):
            demo.validate_payload(payload)

    def test_rejects_missing_or_out_of_order_snapshots(self):
        payload = copy.deepcopy(self.payload)
        payload["iterations"].pop()
        with self.assertRaisesRegex(ValueError, "steps 0 through 50"):
            demo.validate_payload(payload)
        payload = copy.deepcopy(self.payload)
        payload["iterations"][1]["iteration"] = 2
        with self.assertRaisesRegex(ValueError, "contiguous"):
            demo.validate_payload(payload)
        for step, total in ((-1, 50), (51, 50), (0, 0)):
            with self.assertRaises(ValueError):
                demo.draft_text(step, total)

    def test_cli_is_reproducible_and_preserves_arbitrary_svg_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            charts = folder / "charts"
            charts.mkdir()
            unrelated = charts / "my-diagram.svg"
            stale = charts / "999-old-fixture.svg"
            unrelated.write_text("user-owned drawing", encoding="utf-8")
            stale.write_text("stale drawing", encoding="utf-8")
            outputs = []
            for seed in ("0", "731"):
                env = os.environ.copy()
                env["PYTHONHASHSEED"] = seed
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/demo_convergence.py"),
                     "--json-out", str(folder / "data.json"), "--svg-out", str(folder / "overview.svg"),
                     "--charts-dir", str(charts)],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(unrelated.read_text(encoding="utf-8"), "user-owned drawing")
                self.assertEqual(stale.read_text(encoding="utf-8"), "stale drawing")
                outputs.append({path.relative_to(folder): path.read_bytes()
                                for path in folder.rglob("*") if path.is_file()})
            self.assertEqual(outputs[0], outputs[1])
            payload = json.loads(outputs[0][Path("data.json")])
            self.assertEqual(payload, self.payload)
            self.assertEqual(len(list(charts.glob("*.svg"))), len(payload["charts"]) + 2)
            self.assertNotIn("my-diagram.svg", (charts / "README.md").read_text(encoding="utf-8"))

    def test_overview_and_all_folder_charts_match_json_and_are_honestly_labeled(self):
        payload = self.checked
        overview = [chart for chart in payload["charts"] if chart["feature"] in demo.OVERVIEW_CHART_FEATURES]
        self.assertEqual(len(overview), 7)
        self.assertEqual(len(payload["charts"]), 100)
        expected = [(ROOT / "examples/convergence_demo.svg", demo.render_svg(payload, overview))]
        for index, chart in enumerate(payload["charts"], 1):
            filename = demo._chart_filename(index, chart)
            expected.append((ROOT / "examples/convergence_charts" / filename, demo.render_svg(payload, [chart])))
        for path, expected_svg in expected:
            with self.subTest(path=path.name):
                actual = path.read_text(encoding="utf-8")
                self.assertEqual(actual, expected_svg + "\n")
                root = ET.fromstring(actual)
                title = root.find("svg:title", SVG_NS).text
                self.assertIn("Deterministic metric fixture", title)
                self.assertIn("not proof of AI or Salix convergence", actual)
                self.assertNotIn("Validated Sherlock Holmes", actual)
                self.assertNotIn("Base prompt plus Salix", actual)
                lines = root.findall("svg:polyline", SVG_NS)
                self.assertEqual(len(lines), 35 if path.name == "convergence_demo.svg" else 5)
                self.assertEqual({line.attrib["data-series-id"] for line in lines}, {
                    "base_example", "style_example", "salix_inspired_example", "copy_fixture", "benchmark",
                })
                for line in lines:
                    points = line.attrib["points"].split()
                    self.assertEqual(len(points), 51)
                    self.assertEqual(float(points[0].split(",")[0]), 64.0)
                    self.assertEqual(float(points[-1].split(",")[0]), 856.0)
                labels = [node.text for node in root.findall("svg:text", SVG_NS)]
                self.assertIn("50", labels)

    def test_example_docs_disclose_copying_and_the_real_endpoint(self):
        docs = (ROOT / "examples/README.md").read_text(encoding="utf-8")
        index = (ROOT / "examples/convergence_charts/README.md").read_text(encoding="utf-8")
        self.assertIn("never\nproof of AI or Salix convergence", docs)
        self.assertIn("hardcoded illustrations", docs)
        self.assertIn("152 words at step\n49 to 620 words at step 50", docs)
        self.assertIn("exact benchmark", docs)
        self.assertIn("SHA-256", docs)
        self.assertIn("not proof of AI or Salix convergence", index)
        self.assertIn("not observed outputs", index)
        self.assertNotIn("Validated Sherlock Holmes", docs + index)


if __name__ == "__main__":
    unittest.main()
