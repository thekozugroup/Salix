"""Behavioral coverage for source attribution, short samples and portable runtimes."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.io_utils import load_text  # noqa: E402
from lib.social import (  # noqa: E402
    build_profiles,
    comparison,
    digest,
    prepare_record,
    reference_markdown,
    review_draft,
    unique_records,
)
from lib.stats import aggregate, analyze  # noqa: E402

BODY = "We tried a smaller test. It worked. What would you try next?"
OTHER = "Our notes describe the experiment, including its assumptions; the result remains uncertain."


def record(author="author-a", post="one", text=BODY, **fields):
    return dict(schema_version=1, id=post, author_id=author,
                source_url=f"https://example.org/{author}/{post}",
                source_type="original_post", retrieved_at="2026-01-01T12:00:00Z",
                measured_from="original_text", text_complete=True,
                capture_method="synthetic test fixture", original_text=text, **fields)


def external(raw):
    result = copy.deepcopy(raw)
    body = result.pop("original_text")
    result["stats"] = analyze(body)
    result["body_sha256"] = digest(body)
    return result


class SocialRecords(unittest.TestCase):
    def test_short_original_measures_exact_body_without_metadata(self):
        raw = record(summary="A completely different researcher's summary. " * 30)
        measured = prepare_record(raw)
        self.assertEqual(measured["stats"], analyze(BODY))
        self.assertTrue(measured["profile_eligible"])
        self.assertLess(measured["body_word_count"], 300)
        self.assertEqual(measured["body_sha256"], digest(BODY))

    def test_metrics_only_does_not_retain_body(self):
        measured = prepare_record(record(), metrics_only=True)
        self.assertNotIn("original_text", measured)
        self.assertNotIn(BODY, reference_markdown(measured))
        self.assertEqual(measured["stats"], analyze(BODY))

    def test_external_stats_equal_local_measurements(self):
        measured = prepare_record(external(record()))
        self.assertEqual(measured["stats"], prepare_record(record())["stats"])
        self.assertEqual(measured["measurement_origin"], "external_lib.stats.analyze_attestation")
        self.assertTrue(measured["profile_eligible"])

    def test_ineligible_source_never_becomes_author_prose(self):
        for source_type in ("summary", "comment", "repost"):
            raw = record()
            raw["source_type"] = source_type
            local = prepare_record(raw)
            self.assertFalse(local["profile_eligible"])
            self.assertNotIn("stats", local)
            measured = prepare_record(external(raw))
            profile = build_profiles([measured])["profiles"][0]
            self.assertEqual(profile["stats"], {})
            self.assertEqual(profile["sufficiency"]["sample_count"], 0)
            self.assertEqual(len(profile["excluded"]), 1)

    def test_repost_caption_requires_explicit_attribution(self):
        raw = record()
        raw.update(source_type="repost", measured_from="original_caption")
        self.assertFalse(prepare_record(raw)["profile_eligible"])
        raw["attribution_verified"] = True
        self.assertTrue(prepare_record(raw)["profile_eligible"])
        raw["measured_from"] = "reposted_body"
        self.assertFalse(prepare_record(raw)["profile_eligible"])

    def test_complete_text_must_be_explicit(self):
        raw = record()
        raw.pop("text_complete")
        self.assertFalse(prepare_record(raw)["profile_eligible"])
        raw["text_complete"] = "true"
        self.assertFalse(prepare_record(raw)["profile_eligible"])

    def test_invalid_external_stats_and_provenance_rejected(self):
        mutations = [
            lambda r: r.pop("capture_method"),
            lambda r: r.update(body_sha256="made-up"),
            lambda r: r["stats"].pop("word_count"),
            lambda r: r["stats"].update(engagement_score=90),
            lambda r: r["stats"].update(mean_sent_len=float("nan")),
            lambda r: r["stats"].update(mean_sent_len=float("inf")),
            lambda r: r["stats"].update(word_count=True),
            lambda r: r["stats"].update(word_count=-1),
            lambda r: r["stats"].update(char_3grams=[["abc", "invalid"]]),
        ]
        for mutate in mutations:
            raw = external(record())
            mutate(raw)
            with self.assertRaises(ValueError):
                prepare_record(raw)

    def test_reject_empty_prose_overlong_excerpt_and_invalid_counts(self):
        for raw in (record(text=""), record(text="123 !!!"),
                    record(excerpt="word " * 26), record(metrics={"reactions": -1}),
                    record(metrics={"comments": True})):
            with self.assertRaises(ValueError):
                prepare_record(raw)

    def test_reject_path_traversal_and_bad_source(self):
        for field, value in (("id", "../private"), ("author_id", "../../person"),
                             ("source_url", "file:///private"),
                             ("source_url", "https://user:password@example.org"),
                             ("retrieved_at", "unknown")):
            raw = record()
            raw[field] = value
            with self.assertRaises(ValueError):
                prepare_record(raw)

    def test_reference_markdown_has_source_and_is_rejected_as_plain_prose(self):
        measured = prepare_record(record(summary="Research summary."))
        markdown = reference_markdown(measured)
        self.assertIn(measured["source_url"], markdown)
        self.assertLess(markdown.index("Metadata"), markdown.index("Captured text"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.md"
            path.write_text(markdown)
            with self.assertRaisesRegex(ValueError, "paired JSON"):
                load_text(path)


class SocialProfiles(unittest.TestCase):
    def test_author_isolation_and_actual_aggregate(self):
        records = [prepare_record(record()), prepare_record(record(post="two", text=OTHER)),
                   prepare_record(record(author="author-b", text="Yes. I like it!"))]
        profiles = build_profiles(records)["profiles"]
        a, b = profiles
        self.assertEqual(a["stats"], aggregate([analyze(BODY), analyze(OTHER)]))
        self.assertEqual(b["stats"], aggregate([analyze("Yes. I like it!")]))
        self.assertEqual(a["sufficiency"]["sample_count"], 2)
        self.assertEqual(b["sufficiency"]["sample_count"], 1)
        self.assertEqual(a["status"], "provisional")

    def test_both_sufficiency_floors_required(self):
        records = [prepare_record(record())]
        for posts, words in ((2, 1), (1, 1000)):
            profile = build_profiles(records, min_posts=posts, min_words=words)["profiles"][0]
            self.assertFalse(profile["sufficiency"]["thresholds_met"])
        profile = build_profiles(records, min_posts=1, min_words=1)["profiles"][0]
        self.assertEqual(profile["status"], "descriptive")
        with self.assertRaises(ValueError):
            build_profiles(records, min_posts=0)

    def test_dedup_body_and_tracking_url(self):
        first = prepare_record(record())
        body_dup = prepare_record(record(post="another"))
        raw = record(post="third", text=OTHER)
        raw["source_url"] = first["source_url"] + "/?utm_source=test#fragment"
        url_dup = prepare_record(raw)
        kept, skipped = unique_records([first, body_dup, url_dup])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(skipped), 2)

    def test_conflicting_authorship_rejected(self):
        a = prepare_record(record())
        raw = record(author="author-b")
        raw["source_url"] = a["source_url"]
        with self.assertRaisesRegex(ValueError, "conflicting author"):
            unique_records([a, prepare_record(raw)])

    def test_chart_data_retains_unknown_counts_and_provisional_label(self):
        profiles = build_profiles([prepare_record(record(metrics={"reactions": 12}))])
        result = comparison(profiles)
        rows = result["rows"]
        self.assertEqual(next(r["value"] for r in rows if r["metric"] == "reactions"), 12)
        self.assertIsNone(next(r["value"] for r in rows if r["metric"] == "impressions"))
        self.assertTrue(all(r["profile_status"] == "provisional" for r in rows))
        self.assertFalse(any(r["metric"] == "engagement_score" for r in rows))


class DraftReview(unittest.TestCase):
    def test_phrases_case_unicode_whitespace_and_boundaries(self):
        result = review_draft("Do not promise ＧＵＡＲＡＮＴＥＥＤ\nresults. A cartoon is fine.",
                              {"excluded_terms": ["guaranteed results", "art"]})
        self.assertEqual(result["excluded_term_matches"], [{"term": "guaranteed results", "count": 1}])

    def test_default_state_never_implies_approval(self):
        result = review_draft(BODY, {})
        self.assertFalse(result["recorded_checks_pass"])
        self.assertIn("approval_required", result["blockers"])
        self.assertIn("factual_review_required", result["blockers"])

    def test_verified_claim_requires_evidence(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            review_draft(BODY, {"claims": [{"claim": "A claim.", "status": "verified"}]})

    def test_approval_is_bound_to_exact_draft(self):
        policy = {"draft_sha256": digest(BODY), "factual_state": "verified", "approval_state": "approved",
                  "claims": [{"claim": "A claim.", "status": "verified", "evidence": "https://example.org/evidence"}]}
        self.assertTrue(review_draft(BODY, policy)["recorded_checks_pass"])
        self.assertFalse(review_draft(BODY + " Changed.", policy)["recorded_checks_pass"])
        policy["claims"][0]["status"] = "unverified"
        self.assertIn("factual_review_required", review_draft(BODY, policy)["blockers"])


class SocialCLI(unittest.TestCase):
    def run_cli(self, *args, executable=ROOT / "salix"):
        return subprocess.run([sys.executable, str(executable), *map(str, args)],
                              capture_output=True, text=True)

    def test_full_metrics_only_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "input.json"
            source.write_text(json.dumps([record(), external(record(author="author-b", text=OTHER))]))
            refs = base / "refs"
            result = self.run_cli("social", "ingest", source, "--out-dir", refs, "--metrics-only")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(refs.rglob("*.post.json"))), 2)
            for path in refs.rglob("*.post.json"):
                self.assertNotIn("original_text", json.loads(path.read_text()))
            profiles = base / "profiles.json"
            result = self.run_cli("social", "profile", refs, "--out", profiles)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(profiles.read_text())
            self.assertEqual(len(payload["profiles"]), 2)
            chart = base / "chart.json"
            result = self.run_cli("social", "compare", profiles, "--out", chart)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(chart.read_text())["rows"])
            result = self.run_cli("social", "ingest", source, "--out-dir", refs)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reference exists", result.stderr)

    def test_retained_body_roundtrip_recomputes_stats_and_omits_body_from_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "input.json"
            source.write_text(json.dumps(record()))
            refs = base / "refs"
            result = self.run_cli("social", "ingest", source, "--out-dir", refs)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli("social", "profile", refs)
            self.assertEqual(result.returncode, 0, result.stderr)
            post = json.loads(result.stdout)["profiles"][0]["posts"][0]
            self.assertEqual(post["stats"], analyze(BODY))
            self.assertNotIn("original_text", post)

    def test_validation_precedes_batch_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "input.json"
            source.write_text(json.dumps([record(), {"bad": "record"}]))
            result = self.run_cli("social", "ingest", source, "--out-dir", base / "refs")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((base / "refs").exists())

    def test_review_exit_status_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "draft.md").write_text(BODY)
            (base / "policy.json").write_text("{}")
            result = self.run_cli("social", "review", base / "draft.md", "--policy", base / "policy.json")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["recorded_checks_pass"])
            policy = {"draft_sha256": digest(BODY), "factual_state": "verified", "approval_state": "approved"}
            (base / "policy.json").write_text(json.dumps(policy))
            result = self.run_cli("social", "review", base / "draft.md", "--policy", base / "policy.json")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_plugin_bundles_run_without_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/build_skill_bundle.py"),
                                     "--out", str(base / "Salix.skill"), "--all"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for platform in ("codex", "claude"):
                archive = base / f"Salix.{platform}-plugin.zip"
                with zipfile.ZipFile(archive) as zf:
                    names = zf.namelist()
                    self.assertIn(f"salix/.{platform}-plugin/plugin.json", names)
                    self.assertFalse(any("test_social" in n or "__pycache__" in n for n in names))
                    extracted = base / f"extracted-{platform}"
                    zf.extractall(extracted)
                executable = extracted / "salix/skills/salix/salix"
                env = os.environ.copy()
                env.pop("PYTHONPATH", None)
                result = subprocess.run([sys.executable, str(executable), "social", "--help"],
                                         cwd=extracted, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("profile", result.stdout)
                draft = extracted / "draft.md"
                draft.write_text(BODY)
                result = self.run_cli("analyze", draft, "--json", executable=executable)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["word_count"], analyze(BODY)["word_count"])


if __name__ == "__main__":
    unittest.main()
