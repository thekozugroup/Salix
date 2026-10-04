"""Runtime regressions; no optional NLP dependencies or timing thresholds required."""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from lib import io_utils, stats  # noqa: E402
from lib.distance import compute_gaps  # noqa: E402
from lib.tone import heylighen_f_score  # noqa: E402
from scripts import simulate_loop as simulator  # noqa: E402

# Full feature snapshots from 65b6f59, with the stdlib syllable/POS fallbacks.
FEATURE_SNAPSHOTS = [
    ("", "a6440941a9ca0029876219b9395b105716d30d3a249cdae695380e004502b748"),
    (
        "Mr. Smith paid 3.14 dollars. He earned a Ph.D. in the U.S. Now he teaches.",
        "b8c2c95f6d22e9babbf65d248cb0bbc151b9ea1f58942d3bacce4f7df6827502",
    ),
    (
        "Caf\u00e9 r\u00e9sum\u00e9 na\u00efve fa\u00e7ade. "
        "\u041f\u0440\u0438\u0432\u0435\u0442 \u043c\u0438\u0440! "
        "\u039a\u03b1\u03bb\u03b7\u03bc\u03ad\u03c1\u03b1 "
        "\u03ba\u03cc\u03c3\u03bc\u03b5. It is useful, perhaps.\n\n"
        "No terminator here\n\nThen another paragraph.",
        "f3bc2298b9dbd8ce424543f5ad2d6c2479f7127719ae51aaae22b886e2256667",
    ),
    (
        ("The implications of this shift are, perhaps, more subtle than they first appear. "
         "We could build it, though the constraints are real.\n\n" * 8),
        "c14d07e10bd830f034dd3c03e5feaef6b8d96d79125cce29cd847a71bd2c4d8c",
    ),
]


def legacy_split_sentences(text: str) -> list[str]:
    masked = stats.DECIMAL_RE.sub(r"\1" + "\u00b7" + r"\2", text)
    for abbr in stats._ABBR:
        masked = re.sub(
            rf"\b{re.escape(abbr)}\.(?=\s|$)",
            lambda m, a=abbr: f"{a}\u00b7",
            masked,
            flags=re.IGNORECASE,
        )
    return [part.replace("\u00b7", ".").strip()
            for part in stats.SENT_SPLIT_RE.split(masked) if part.strip()]


def expected_ngrams(sequence: list[str], n: int) -> list[list]:
    counts = Counter(" ".join(sequence[i:i + n]) for i in range(len(sequence) - n + 1))
    total = sum(counts.values()) or 1
    return [[gram, round(count / total, 6)] for gram, count in counts.most_common(100)]


def keep_patch(test_case: unittest.TestCase, patcher):
    replacement = patcher.start()
    test_case.addCleanup(patcher.stop)
    return replacement


class TestRuntimeStats(unittest.TestCase):
    def setUp(self):
        keep_patch(self, patch.object(stats, "_get_spacy_nlp", return_value=None))
        keep_patch(self, patch.object(stats, "_get_pyphen", return_value=None))
        stats.estimate_syllables.cache_clear()
        self.addCleanup(stats.estimate_syllables.cache_clear)

    def test_full_feature_snapshots_unchanged(self):
        for text, expected_digest in FEATURE_SNAPSHOTS:
            with self.subTest(text=text[:40]):
                features = stats.analyze(text)
                serialized = json.dumps(features, sort_keys=True, ensure_ascii=True).encode()
                self.assertEqual(hashlib.sha256(serialized).hexdigest(), expected_digest)

    def test_abbreviation_mask_matches_legacy(self):
        texts = [
            " ".join(f"{abbr.upper()}. Name." for abbr in sorted(stats._ABBR)),
            "\u0130NC. builds things. \u0131.e. examples. \u017fT. Paul. U.\u212a. law.",
            'He said "Wait." Then left. Why?! Fine... ok. 3.14 1.2.3. End.',
            "a\u00b7b. Dr.\n\nSmith arrived. etc.\tNow?\nYes!",
            "", "...", "No terminator\n\nSecond paragraph",
        ]
        rng = random.Random(17)
        fragments = ["Mr. Smith", "e.g. this", "Ph.D. research", "etc.", "p.m. now",
                     "3.14", "wait...", "Really?!", "ok.", "word", "\n\n", '"End."']
        texts.extend(" ".join(rng.choices(fragments, k=20)) for _ in range(100))
        for text in texts:
            with self.subTest(text=text[:60]):
                self.assertEqual(stats.split_sentences(text), legacy_split_sentences(text))

    def test_abbreviation_pattern_is_not_recompiled(self):
        with patch.object(stats.re, "compile", wraps=re.compile) as compile_pattern:
            for _ in range(3):
                stats.split_sentences("Dr. Smith teaches. Prof. Jones listens.")
        compile_pattern.assert_not_called()

    def test_sentence_tokens_and_character_normalization_are_reused(self):
        text = "First words occur. Another line ends.\n\nThird segment returns."
        with patch.object(stats, "tokenize", wraps=stats.tokenize) as tokenize_words, \
                patch.object(stats, "_normalize_chars", wraps=stats._normalize_chars) as normalize:
            stats.analyze(text)
        # One raw-text pass, three sentence passes, two independent paragraph passes.
        self.assertEqual(tokenize_words.call_count, 6)
        normalize.assert_called_once_with(text)

    def test_analyze_shares_one_token_counter(self):
        names = ["lexical_features", "yule_k", "honore_r", "simpson_d", "readability",
                 "function_word_rates", "burrows_delta_features"]
        spies = [keep_patch(self, patch.object(stats, name, wraps=getattr(stats, name)))
                 for name in names]
        stats.analyze("the cat and the dog. " * 20)
        shared_counts = spies[0].call_args.kwargs["counts"]
        self.assertEqual(shared_counts, Counter({"the": 40, "cat": 20, "and": 20, "dog": 20}))
        for spy in spies:
            self.assertIs(spy.call_args.kwargs["counts"], shared_counts)

    def test_public_helpers_preserve_calls_and_frequency_order(self):
        for tokens in [[], ["one"], "of the and but of the and but unique".split() * 10]:
            counts = Counter(tokens)
            before = counts.copy()
            for name in ["lexical_features", "yule_k", "honore_r", "simpson_d"]:
                fn = getattr(stats, name)
                self.assertEqual(fn(tokens), fn(tokens, counts=counts))
            self.assertEqual(stats.function_word_rates(tokens, len(tokens)),
                             stats.function_word_rates(tokens, len(tokens), counts=counts))
            self.assertEqual(stats.burrows_delta_features(tokens, len(tokens), 3),
                             stats.burrows_delta_features(tokens, len(tokens), 3, counts=counts))
            self.assertEqual(stats.readability(tokens, ["One sentence."]),
                             stats.readability(tokens, ["One sentence."], counts=counts))
            self.assertEqual(counts, before)
        self.assertEqual([word for word, _ in stats.burrows_delta_features(tokens, len(tokens), 3)],
                         ["of", "the", "and"])

    def test_readability_estimates_each_type_once(self):
        tokens = ["one", "three"] * 100
        with patch.object(stats, "estimate_syllables", side_effect={"one": 1, "three": 3}.get) as estimate:
            result = stats.readability(tokens, ["First.", "Second."])
        self.assertEqual(estimate.call_args_list, [call("one"), call("three")])
        self.assertEqual(result, {
            "flesch_kincaid_grade": 0.39 * 100 + 11.8 * 2 - 15.59,
            "gunning_fog": 0.4 * (100 + 100.0 * 100 / 200),
            "ari": 4.71 * 4 + 0.5 * 100 - 21.43,
        })

    def test_spacy_counts_and_ngrams_use_one_document(self):
        tags = ["DET", "NOUN", "SPACE", "VERB", "PUNCT", "PROPN", "ADJ", "ADV", "AUX",
                "PRON", "DET", "ADP", "INTJ", "SYM", "X", "NOUN", "PUNCT"]
        nlp = Mock(side_effect=lambda text: [SimpleNamespace(pos_=tag) for tag in tags])
        text = "The dog runs. The cat sits."
        expected_counts = {"noun": 3, "adj": 1, "adv": 1, "verb": 2,
                           "pron": 1, "article": 2, "prep": 1, "interj": 1}
        with patch.object(stats, "_get_spacy_nlp", return_value=nlp):
            result = stats.analyze(text)
            nlp.assert_called_once_with(text)
            # Do not persist POS results across analyses of the same text.
            self.assertEqual(stats.analyze(text), result)
            self.assertEqual(nlp.call_count, 2)
            self.assertEqual(stats._spacy_pos_counts(text), expected_counts)
            self.assertEqual(stats._spacy_pos_sequence(text), [t for t in tags if t != "SPACE"])
            self.assertEqual(stats.pos_ngrams(text), result["pos_bigrams"])
        self.assertEqual(result["formality_source"], "spacy")
        self.assertEqual(result["formality_f_score"],
                         round(heylighen_f_score(expected_counts, result["word_count"]), 3))
        sequence = [tag for tag in tags if tag != "SPACE"]
        self.assertEqual(result["pos_bigrams"], expected_ngrams(sequence, 2))
        self.assertEqual(result["pos_trigrams"], expected_ngrams(sequence, 3))

    def test_missing_spacy_keeps_fallback_and_empty_ngrams(self):
        result = stats.analyze("One sentence.")
        self.assertEqual(result["formality_source"], "suffix_proxy")
        self.assertEqual(result["pos_bigrams"], [])
        self.assertEqual(result["pos_trigrams"], [])


class TestBoundedFileRead(unittest.TestCase):
    def test_oversized_file_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(io_utils, "MAX_FILE_BYTES", 16):
            path = Path(tmp) / "large.txt"
            path.write_bytes(b"x" * 17)
            with patch.object(Path, "open") as open_file:
                with self.assertRaisesRegex(ValueError, "17 bytes; exceeds MAX_FILE_BYTES"):
                    io_utils.load_text(path)
            open_file.assert_not_called()

    def test_exact_byte_limit_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(io_utils, "MAX_FILE_BYTES", 16):
            path = Path(tmp) / "exact.txt"
            path.write_bytes(b"x" * 16)
            self.assertEqual(io_utils.load_text(path), "x" * 16)

    def test_read_remains_bounded_when_stat_is_stale(self):
        path = MagicMock(spec=Path)
        path.stat.return_value = SimpleNamespace(st_size=1)
        stream = path.open.return_value.__enter__.return_value
        stream.read.side_effect = lambda size: b"x" * size
        with patch.object(io_utils, "MAX_FILE_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "exceeds MAX_FILE_BYTES"):
                io_utils._read_with_fallback(path)
        path.open.assert_called_once_with("rb")
        stream.read.assert_called_once_with(17)
        path.open.return_value.__exit__.assert_called_once()

    def test_actual_growth_after_stat_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(io_utils, "MAX_FILE_BYTES", 16):
            path = Path(tmp) / "grown.txt"
            path.write_bytes(b"x" * 32)
            with patch.object(Path, "stat", return_value=SimpleNamespace(st_size=1)):
                with self.assertRaisesRegex(ValueError, "exceeds MAX_FILE_BYTES"):
                    io_utils.load_text(path)

    def test_encoding_fallbacks_and_bom_are_preserved(self):
        cases = [(b"\xef\xbb\xbfHello.", "Hello."),
                 (b"caf\xc3\xa9", "caf\u00e9"),
                 (b"He said \x93hello\x94.", "He said \u201chello\u201d."),
                 (b"Latin \x81 byte.", "Latin \u0081 byte.")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "encoding.txt"
            for raw, expected in cases:
                with self.subTest(raw=raw), patch.object(io_utils, "MAX_FILE_BYTES", len(raw)):
                    path.write_bytes(raw)
                    self.assertEqual(io_utils.load_text(path), expected)

    def test_missing_file_preserves_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                io_utils.load_text(Path(tmp) / "missing.txt")


def gap_report(distance: float) -> dict:
    return {"total_distance": distance,
            "top_gaps": [{"feature": "punct_comma_per1k", "z_distance": -1.0}]}


class TestSimulatorRuntime(unittest.TestCase):
    def mock_loop(self, distances: dict[str, float]):
        analyze = keep_patch(self, patch.object(simulator, "analyze", side_effect=lambda text: text))
        keep_patch(self, patch.object(simulator, "compute_gaps",
                                     side_effect=lambda text, bench: gap_report(distances[text])))
        edits = keep_patch(self, patch.object(simulator, "pick_edits", return_value=[
            (lambda text: text + "!", {"feature": "punct_comma_per1k"}),
        ]))
        return analyze, edits

    def test_max_iter_records_final_edit_and_reuses_accepted_score(self):
        analyze, _ = self.mock_loop({"start": 3.0, "start!": 2.0, "start!!": 1.0})
        result = simulator.run_loop("start", {}, max_iter=2, threshold=0.0)
        self.assertEqual(analyze.call_args_list, [call("start"), call("start!"), call("start!!")])
        self.assertEqual(result["stop_reason"], "max_iter")
        self.assertEqual(result["final_text"], "start!!")
        self.assertEqual(result["final_distance"], 1.0)
        self.assertEqual(result["initial_distance"], 3.0)
        self.assertAlmostEqual(result["improvement_pct"], 200 / 3)
        self.assertEqual([h["distance"] for h in result["history"]], [3.0, 2.0, 1.0])
        self.assertEqual([h["iter"] for h in result["history"]], [0, 1, 2])
        self.assertNotIn("applied_edit", result["history"][-1])
        self.assertTrue(all(h["applied_edit"] == "punct_comma_per1k"
                            for h in result["history"][:-1]))

    def test_final_allowed_edit_can_converge(self):
        self.mock_loop({"start": 3.0, "start!": 0.1})
        result = simulator.run_loop("start", {}, max_iter=1, threshold=0.15)
        self.assertEqual(result["stop_reason"], "converged")
        self.assertEqual(result["final_distance"], 0.1)
        self.assertEqual(result["history"][-1]["status"], "converged")

    def test_zero_iterations_measures_initial_text_without_editing(self):
        analyze, edits = self.mock_loop({"start": 3.0})
        result = simulator.run_loop("start", {}, max_iter=0, threshold=0.15)
        analyze.assert_called_once_with("start")
        edits.assert_not_called()
        self.assertEqual(result["final_text"], "start")
        self.assertEqual(result["final_distance"], 3.0)
        self.assertEqual(result["initial_distance"], 3.0)
        self.assertEqual(result["improvement_pct"], 0.0)
        self.assertEqual(result["stop_reason"], "max_iter")
        self.assertEqual(len(result["history"]), 1)

    def test_zero_distance_does_not_divide_by_zero(self):
        self.mock_loop({"start": 0.0})
        result = simulator.run_loop("start", {}, max_iter=0, threshold=0.15)
        self.assertEqual(result["stop_reason"], "converged")
        self.assertEqual(result["improvement_pct"], 0.0)

    def test_negative_iteration_budget_is_rejected_before_scoring(self):
        with patch.object(simulator, "analyze") as analyze:
            with self.assertRaisesRegex(ValueError, "max_iter must be non-negative"):
                simulator.run_loop("start", {}, max_iter=-1, threshold=0.15)
        analyze.assert_not_called()

    def test_rejected_edit_leaves_final_metrics_unchanged(self):
        self.mock_loop({"start": 3.0, "start!": 4.0})
        result = simulator.run_loop("start", {}, max_iter=2, threshold=0.0)
        self.assertEqual(result["stop_reason"], "no_applicable_rule_changed_text")
        self.assertEqual(result["final_text"], "start")
        self.assertEqual(result["final_distance"], 3.0)
        self.assertEqual(len(result["history"]), 1)
        self.assertNotIn("applied_edit", result["history"][0])

    def test_rejected_candidate_falls_through_to_next_rule(self):
        analyze, edits = self.mock_loop({"start": 3.0, "start?": 4.0, "start!": 2.0})
        edits.return_value = [(lambda text: text + "?", {"feature": "rejected"}),
                              (lambda text: text + "!", {"feature": "accepted"})]
        result = simulator.run_loop("start", {}, max_iter=1, threshold=0.0)
        self.assertEqual(analyze.call_args_list, [call("start"), call("start?"), call("start!")])
        self.assertEqual(result["final_distance"], 2.0)
        self.assertEqual(result["history"][0]["applied_edit"], "accepted")

    def test_plateau_preserves_last_scored_state(self):
        self.mock_loop({"start": 3.0, "start!": 3.0, "start!!": 3.0})
        result = simulator.run_loop("start", {}, max_iter=4, threshold=0.0)
        self.assertEqual(result["stop_reason"], "plateau")
        self.assertEqual(result["final_text"], "start!!")
        self.assertEqual(result["final_distance"], result["history"][-1]["distance"])

    def test_verbose_logs_go_to_stderr(self):
        self.mock_loop({"start": 3.0, "start!": 2.0})
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            simulator.run_loop("start", {}, max_iter=1, threshold=0.0, verbose=True)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("iter 0:", stderr.getvalue())
        self.assertIn("iter 1:", stderr.getvalue())
        self.assertIn("applied edit", stderr.getvalue())


class TestSimulatorCLI(unittest.TestCase):
    def test_json_verbose_and_saved_text_match_final_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "benchmarks").mkdir()
            benchmark = stats.analyze("The author writes, perhaps, deliberately. " * 10)
            (home / "benchmarks" / "runtime.json").write_text(
                json.dumps({"schema_version": 2, "stats": benchmark}), encoding="utf-8")
            draft = home / "draft.txt"
            draft.write_text("It works and people like it. Users are happy.", encoding="utf-8")
            out = home / "result.txt"
            result = subprocess.run(
                [sys.executable, str(ROOT / "salix"), "simulate", str(draft),
                 "--home", str(home), "--profile", "runtime", "--max-iter", "1",
                 "--threshold", "0", "--json", "--verbose", "--out", str(out)],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("iter 0:", result.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), payload["final_text"])
            final = compute_gaps(stats.analyze(payload["final_text"]), benchmark)["total_distance"]
            self.assertEqual(payload["final_distance"], final)
            self.assertEqual(payload["history"][-1]["distance"], final)

    def test_standalone_zero_iterations_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = root / "draft.txt"
            draft.write_text("It works.", encoding="utf-8")
            bench = root / "benchmark.json"
            bench.write_text(json.dumps(stats.analyze("An entirely different sentence.")),
                             encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "simulate_loop.py"),
                 "--target-text", str(draft), "--benchmark", str(bench),
                 "--max-iter", "0", "--threshold", "0", "--verbose"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Stop reason: max_iter", result.stdout)
            self.assertIn("Iterations:  0", result.stdout)
            self.assertIn("iter 0:", result.stderr)


if __name__ == "__main__":
    unittest.main()
