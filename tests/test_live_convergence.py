import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from live_convergence import (  # noqa: E402
    ModelCallFailure,
    child_environment,
    fallback_metrics,
    model_call,
    phrases,
    safe_events,
    screen,
    select_corpus,
    validate_payload,
)
from render_live_convergence import prepare_charts  # noqa: E402

from lib import stats as stats_module  # noqa: E402


class LiveExperimentHelpersTests(unittest.TestCase):
    def test_whitelisted_events_never_preserve_raw_metadata(self):
        raw = "\n".join(json.dumps(event) for event in [
            {"type": "thread.started", "secret": "not-for-storage"},
            {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3,
                                                  "api_key": "not-for-storage"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "public draft"}},
        ])
        record = safe_events(raw)
        self.assertEqual(record["usage"], [{"input_tokens": 12, "output_tokens": 3}])
        self.assertEqual(record["agent_texts"], ["public draft"])
        self.assertNotIn("not-for-storage", json.dumps(record))

    def test_known_tool_calls_are_detected(self):
        for item_type in ("command_execution", "mcp_tool_call", "web_search", "file_change"):
            record = safe_events(json.dumps({"type": "item.completed", "item": {"type": item_type}}))
            self.assertEqual(record["tool_events"], 1)

    def test_unknown_tool_calls_fail_closed(self):
        record = safe_events(json.dumps({"type": "item.completed", "item": {"type": "new_tool_type"}}))
        self.assertEqual(record["tool_events"], 1)

    def test_child_environment_excludes_unrelated_secrets(self):
        with patch.dict(os.environ, {"PRIVATE_API_TOKEN": "synthetic-only-secret", "PATH": "/usr/bin"}):
            env = child_environment(Path("/tmp/isolated"))
        self.assertNotIn("PRIVATE_API_TOKEN", env)
        self.assertEqual(env["HOME"], "/tmp/isolated")

    def test_secret_output_is_redacted_and_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            secret = "SYNTHETIC_ONLY_TOKEN_123"

            def respond(*args, **kwargs):
                self.assertNotIn("PRIVATE_API_TOKEN", kwargs["env"])
                (home / "response.txt").write_text(secret)
                events = [{"type": "item.completed", "item": {"type": "agent_message", "text": secret}},
                          {"type": "turn.completed", "usage": {"output_tokens": 4}}]
                return subprocess.CompletedProcess(args[0], 0, "\n".join(map(json.dumps, events)), "")

            with patch.dict(os.environ, {"PRIVATE_API_TOKEN": secret}), patch("live_convergence.subprocess.run", side_effect=respond):
                with self.assertRaises(ModelCallFailure) as caught:
                    model_call("public prompt", "codex", "test-model", home, 30)
            self.assertNotIn(secret, json.dumps(caught.exception.record))
            self.assertEqual(caught.exception.record["partial_text"], "[REDACTED]")
            self.assertEqual(caught.exception.record["outcome"], "secret_redaction")

    def test_failed_call_keeps_sanitized_partial_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            partial = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Partial public draft"}})
            with patch("live_convergence.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 1, output=partial)):
                with self.assertRaises(ModelCallFailure) as caught:
                    model_call("record this prompt", "codex", "test-model", Path(temporary), 1)
            self.assertEqual(caught.exception.record["partial_text"], "Partial public draft")
            self.assertEqual(caught.exception.record["prompt"], "record this prompt")
            self.assertEqual(caught.exception.record["outcome"], "TimeoutExpired")

    def test_fallback_clears_other_backend_syllable_cache(self):
        stats_module.estimate_syllables.cache_clear()

        class FakeDictionary:
            def inserted(self, word):
                return "one-two-three-four-five-six-seven-eight-nine"

        with patch.object(stats_module, "_get_pyphen", return_value=FakeDictionary()):
            self.assertEqual(stats_module.estimate_syllables("cat"), 9)
        with fallback_metrics():
            self.assertEqual(stats_module.estimate_syllables("cat"), 1)
        self.assertEqual(stats_module.estimate_syllables.cache_info().currsize, 0)

    def test_eight_word_copying_is_screened(self):
        source = "one two three four five six seven eight nine"
        self.assertIn("eight-word source overlap", screen(source, phrases(source)))

    def test_apostrophe_variants_do_not_evade_copy_screen(self):
        source = "he didn't think the woman's ticket had been stolen"
        variant = source.replace("'", "’")
        self.assertIn("eight-word source overlap", screen(variant, phrases(source)))

    def test_screen_is_explicitly_lexical_not_semantic(self):
        failures = screen("Clara Bell went to Euston at 6:40.", set())
        self.assertIn("missing factual token: rain", failures)
        self.assertIn("outside 400-550 whitespace words", failures)

    def test_source_selection_uses_disjoint_stories(self):
        numbers = ("I", "II", "III", "IV", "V", "VI")
        source = "\n\n".join(f"{number}. STORY {chr(65 + index)}\n\n" + "word " * 510
                               for index, number in enumerate(numbers))
        corpus = select_corpus(source)
        self.assertEqual(len(corpus["training"]), 3)
        self.assertEqual(len(corpus["heldout"]), 3)
        self.assertFalse({sample["story"] for sample in corpus["training"]} &
                         {sample["story"] for sample in corpus["heldout"]})

    def test_missing_source_stories_rejected(self):
        with self.assertRaisesRegex(ValueError, "six story headings"):
            select_corpus("Not a six-story source.")


@unittest.skipUnless((ROOT / "examples/live_convergence.json").is_file(), "Live record not generated")
class RecordedExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "examples/live_convergence.json").read_text(encoding="utf-8"))
        if len(cls.payload.get("calls", [])) < 3:
            raise unittest.SkipTest("Record needs both baselines and at least one completed rewrite")

    def test_published_record_has_fifty_completed_attempts(self):
        if self.payload["completion"]["status"] == "running":
            self.skipTest("Generation in progress; publication check follows completion")
        self.assertEqual(self.payload["completion"]["status"], "attempt_budget_exhausted")
        self.assertEqual(self.payload["completion"]["attempts"], 50)
        self.assertEqual(len(self.payload["calls"]), 52)
        self.assertEqual(len(self.payload["iterations"]), 51)
        self.assertEqual(self.payload["failures"], [])

    def test_every_record_is_remeasured_and_selection_replayed(self):
        validate_payload(self.payload)

    def test_tampered_text_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["calls"][0]["text"] += " Modified."
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_payload(payload)

    def test_false_convergence_claim_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["completion"]["convergence_proven"] = True
        with self.assertRaisesRegex(ValueError, "convergence claims"):
            validate_payload(payload)

    def test_heldout_feedback_leak_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["calls"][2]["prompt"] += payload["corpus"]["heldout"][0]["text"]
        with self.assertRaisesRegex(ValueError, "held-out feedback leak"):
            validate_payload(payload)

    def test_candidate_rejections_cannot_disappear_from_chart(self):
        charts, attempts, _ = prepare_charts(self.payload)
        self.assertGreaterEqual(len(charts), 100)
        self.assertTrue(all(len(line["values"]) == attempts + 1 for chart in charts for line in chart["series"]))
        self.assertTrue(all({line["id"] for line in chart["series"]} ==
                            {"candidate", "retained", "base", "style", "benchmark"} for chart in charts))


if __name__ == "__main__":
    unittest.main()
