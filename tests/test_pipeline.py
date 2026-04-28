"""Smoke tests covering the full Salix pipeline.

Run with:  python3 -m unittest discover tests/
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.io_utils import clean_text  # noqa: E402
from lib.stats import analyze, aggregate, mtld, split_sentences, tokenize  # noqa: E402
from lib.distance import compute_gaps  # noqa: E402


SAMPLE_FORMAL = """
The implications of this shift are, perhaps, more subtle than they first appear.
One could argue that the architecture itself imposes constraints; indeed, those
constraints shape the resulting style. The author writes deliberately, choosing
each subordinate clause with care. Rather than rush, the prose unfolds slowly,
turning over each idea before committing it to the page. There is, however, a
risk: such restraint may read as airless. The remedy is not abandonment of form
but variation within it. A short sentence, here, breaks the cadence. Then the
longer one returns, carrying the next thought through its full arc.
"""

SAMPLE_CASUAL = """
Look — the thing is, I just don't buy it. You can dress this up however you
want, but at the end of the day it's the same idea we've been kicking around
for years. Maybe I'm wrong! Maybe there's something I'm missing. But every
time I look at the numbers, the answer comes back: nope. We've tried this.
It didn't work. So why is everyone acting like it's brand new? I guess I'm
just tired.
"""

TARGET_DRAFT = """
The system has been redesigned. New features were added. Performance is
better now. Users seem happy with the changes. There were some bugs but
those got fixed. Overall it's working as intended.
"""


class TestStats(unittest.TestCase):
    def test_tokenize(self):
        toks = tokenize("Hello, world. It's working!")
        self.assertIn("hello", toks)
        self.assertIn("world", toks)
        self.assertIn("it's", toks)

    def test_split_sentences(self):
        s = split_sentences("Mr. Smith arrived. He was late. So what?")
        self.assertEqual(len(s), 3)

    def test_split_sentences_lowercase_prose(self):
        # Casual / unedited prose without capitals must still segment.
        s = split_sentences("ok so here's the thing. i've been using it. it works fine.")
        self.assertEqual(len(s), 3)

    def test_split_sentences_protects_decimals(self):
        s = split_sentences("The value rose to 3.14 today. Then it fell.")
        self.assertEqual(len(s), 2)

    def test_split_sentences_handles_ellipsis_and_interrobang(self):
        s = split_sentences("Wait... what? Really?! No.")
        self.assertEqual(len(s), 4)

    def test_split_sentences_protects_abbreviations(self):
        s = split_sentences("She earned a Ph.D. last year. Now she teaches.")
        self.assertEqual(len(s), 2)

    def test_mtld(self):
        v = mtld(tokenize(SAMPLE_FORMAL))
        self.assertGreater(v, 0)

    def test_clean_text_strips_code_and_urls(self):
        raw = "See `inline` and ```block``` here. Visit http://example.com please."
        cleaned = clean_text(raw)
        self.assertNotIn("inline", cleaned)
        self.assertNotIn("block", cleaned)
        self.assertNotIn("example.com", cleaned)

    def test_clean_text_strips_code_blocks_before_url_pass(self):
        """A URL inside a fenced block must not leak into the cleaned text."""
        raw = "Prose. ```\ncode at http://leak.example.com\n``` More prose."
        cleaned = clean_text(raw)
        self.assertNotIn("leak.example.com", cleaned)
        self.assertNotIn("code at", cleaned)

    def test_clean_text_em_dash_not_treated_as_bullet(self):
        """Em-dash-led narration must survive clean_text untouched."""
        raw = "He paused. — She replied. — They left."
        cleaned = clean_text(raw)
        self.assertIn("—", cleaned)
        self.assertIn("She replied", cleaned)

    def test_clean_text_image_does_not_leak(self):
        raw = "Caption: ![alt text here](path/to.png) and prose."
        cleaned = clean_text(raw)
        self.assertNotIn("alt text", cleaned)
        self.assertNotIn("path/to", cleaned)
        self.assertIn("Caption:", cleaned)

    def test_word_re_handles_accented_latin(self):
        from lib.stats import tokenize as _tok
        toks = _tok("Café résumé naïve façade")
        self.assertEqual(len(toks), 4)
        self.assertIn("café", toks)
        self.assertIn("résumé", toks)

    def test_load_text_falls_back_on_cp1252(self):
        """CP1252 smart-quotes must decode without silent U+FFFD substitution."""
        from lib.io_utils import load_text as _load
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            # 0x93 = "smart left double quote" in CP1252; invalid UTF-8.
            fh.write(b"He said \x93hello\x94 to her.")
            tmp_path = fh.name
        try:
            text = _load(Path(tmp_path))
            self.assertNotIn("�", text)
            self.assertIn("hello", text)
        finally:
            Path(tmp_path).unlink()

    def test_load_text_strips_bom(self):
        from lib.io_utils import load_text as _load
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            fh.write(b"\xef\xbb\xbfHello world.")
            tmp_path = fh.name
        try:
            text = _load(Path(tmp_path))
            self.assertTrue(text.startswith("Hello"))
        finally:
            Path(tmp_path).unlink()

    def test_load_corpus_dedupes_symlinks(self):
        from lib.io_utils import load_corpus as _lc
        import os as _os
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "real.md").write_text(SAMPLE_FORMAL)
            try:
                _os.symlink(d / "real.md", d / "link.md")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unsupported on this platform")
            corpus = _lc(d)
            # corpus should not double-count the same canonical file
            occurrences = corpus.count("The implications of this shift")
            self.assertEqual(occurrences, 1)

    def test_analyze_returns_required_keys(self):
        s = analyze(SAMPLE_FORMAL)
        for k in ["word_count", "ttr", "mtld", "mean_sent_len",
                  "flesch_kincaid_grade", "formality_f_score",
                  "hedging_rate", "fw_bigrams", "sentence_starters"]:
            self.assertIn(k, s, f"missing {k}")
        self.assertGreater(s["word_count"], 50)
        self.assertGreater(s["mean_sent_len"], 5)

    def test_formal_vs_casual_diverge(self):
        formal = analyze(SAMPLE_FORMAL)
        casual = analyze(SAMPLE_CASUAL)
        # formal should score higher on F-score than casual
        self.assertGreater(formal["formality_f_score"], casual["formality_f_score"])
        # casual has more first-person pronouns
        self.assertGreater(casual["fw_i_per1k"], formal["fw_i_per1k"])

    def test_aggregate_two_samples(self):
        s1 = analyze(SAMPLE_FORMAL)
        s2 = analyze(SAMPLE_CASUAL)
        agg = aggregate([s1, s2])
        self.assertEqual(agg["sample_count"], 2)
        self.assertEqual(agg["total_word_count"], s1["word_count"] + s2["word_count"])
        self.assertIn("fw_bigrams", agg)

    def test_aggregate_emits_empirical_sigma(self):
        """With multiple samples, _sigma must capture per-feature variance."""
        s1 = analyze(SAMPLE_FORMAL)
        s2 = analyze(SAMPLE_CASUAL)
        s3 = analyze(SAMPLE_FORMAL[:300])
        agg = aggregate([s1, s2, s3])
        self.assertIn("_sigma", agg)
        # Sigma should exist for every scalar feature
        for k in ["mean_sent_len", "ttr", "formality_f_score"]:
            self.assertIn(k, agg["_sigma"], f"missing empirical sigma for {k}")
        # Sigma must be non-negative
        for k, v in agg["_sigma"].items():
            self.assertGreaterEqual(v, 0.0)
        # Mean sentence length varies between formal/casual — sigma must be > 0
        self.assertGreater(agg["_sigma"]["mean_sent_len"], 0.0)

    def test_aggregate_single_sample_has_empty_sigma(self):
        s1 = analyze(SAMPLE_FORMAL)
        agg = aggregate([s1])
        self.assertEqual(agg.get("_sigma"), {})

    def test_function_word_ngrams_run_based(self):
        """N-grams should come from FW runs only and not cross content tokens."""
        from lib.stats import function_word_ngrams as fwn
        # "the of and" is a contiguous FW run; "the dog of" has dog breaking it
        toks = "the of and to a dog the of a".split()
        bigrams = dict(fwn(toks, n=2, top_k=20))
        # "the of" appears in run 1; "the of" again as a fragment of "the of a"
        self.assertIn("the of", bigrams)
        # "of dog" must NOT appear (dog is a content word)
        self.assertNotIn("of dog", bigrams)
        # Frequencies sum to 1
        self.assertAlmostEqual(sum(bigrams.values()), 1.0, places=4)


class TestDistance(unittest.TestCase):
    def test_identical_distance_zero(self):
        s = analyze(SAMPLE_FORMAL)
        gaps = compute_gaps(s, s)
        self.assertLess(gaps["total_distance"], 0.05)

    def test_different_styles_have_distance(self):
        formal = analyze(SAMPLE_FORMAL)
        target = analyze(TARGET_DRAFT)
        gaps = compute_gaps(target, formal)
        self.assertGreater(gaps["total_distance"], 0.5)
        # top gaps should populate
        self.assertGreater(len(gaps["top_gaps"]), 0)
        # each gap should have a suggestion
        for g in gaps["top_gaps"]:
            self.assertIn("suggestion", g)
            self.assertTrue(g["suggestion"])

    def test_top_gaps_sorted_by_magnitude(self):
        formal = analyze(SAMPLE_FORMAL)
        target = analyze(TARGET_DRAFT)
        gaps = compute_gaps(target, formal)
        zs = [g["abs_z"] for g in gaps["top_gaps"]]
        self.assertEqual(zs, sorted(zs, reverse=True))

    def test_gaps_include_actionable_edit_hints(self):
        formal = analyze(SAMPLE_FORMAL)
        target = analyze(TARGET_DRAFT)
        gaps = compute_gaps(target, formal)
        # At least the top gap must have direction + a non-empty edit hint.
        top = gaps["top_gaps"][0]
        self.assertIn(top["direction"], ("raise", "lower"))
        self.assertTrue(top["edit_hint"], "top gap should have an edit hint")
        # Most top-10 gaps should have hints (>=70%)
        with_hints = sum(1 for g in gaps["top_gaps"] if g.get("edit_hint"))
        self.assertGreaterEqual(with_hints, 7)


class TestEndToEnd(unittest.TestCase):
    def test_full_ingest_and_compare(self):
        with tempfile.TemporaryDirectory() as tmp:
            samples_dir = Path(tmp) / "samples"
            samples_dir.mkdir()
            # repeat samples to clear min-words bar
            (samples_dir / "a.md").write_text((SAMPLE_FORMAL + "\n") * 6)
            (samples_dir / "b.md").write_text((SAMPLE_FORMAL + "\n") * 6)

            bench_path = Path(tmp) / "bench.json"
            import subprocess
            res = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "ingest.py"),
                 "--samples", str(samples_dir),
                 "--out", str(bench_path),
                 "--name", "test",
                 "--min-words", "100"],
                capture_output=True, text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(bench_path.exists())
            data = json.loads(bench_path.read_text())
            self.assertEqual(data["name"], "test")
            self.assertGreater(data["stats"]["total_word_count"], 500)


class TestCLI(unittest.TestCase):
    """Verify the unified `salix` CLI dispatches each subcommand correctly."""

    def test_help(self):
        import subprocess
        res = subprocess.run(
            [sys.executable, str(ROOT / "salix"), "help"],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("salix status", res.stdout)
        self.assertIn("salix ingest", res.stdout)

    def test_status(self):
        import subprocess
        res = subprocess.run(
            [sys.executable, str(ROOT / "salix"), "status"],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Salix root:", res.stdout)

    def test_ingest_then_compare_via_cli(self):
        """End-to-end CLI test, fully isolated via SALIX_HOME — never writes
        to the installed skill's benchmarks/ dir."""
        import os as _os
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            (home / "samples").mkdir()
            (home / "benchmarks").mkdir()
            samples_dir = home / "samples"
            (samples_dir / "a.md").write_text((SAMPLE_FORMAL + "\n") * 6)
            (samples_dir / "b.md").write_text((SAMPLE_FORMAL + "\n") * 6)

            env = {**_os.environ, "SALIX_HOME": str(home)}
            res = subprocess.run(
                [sys.executable, str(ROOT / "salix"), "ingest",
                 "--name", "_clitest", "--min-words", "100"],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((home / "benchmarks" / "_clitest.json").exists())

            draft = Path(tmp) / "draft.md"
            draft.write_text(TARGET_DRAFT)
            res2 = subprocess.run(
                [sys.executable, str(ROOT / "salix"), "compare",
                 str(draft), "--profile", "_clitest", "--json"],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(res2.returncode, 0, res2.stderr)
            report = json.loads(res2.stdout)
            self.assertIn("total_distance", report)
            self.assertGreater(report["total_distance"], 0.5)

    def test_version_flag(self):
        import subprocess
        res = subprocess.run(
            [sys.executable, str(ROOT / "salix"), "--version"],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("salix", res.stdout.lower())


class TestSimulator(unittest.TestCase):
    """Validate the rewrite-loop mechanics using the rule-based simulator."""

    def test_simulator_decreases_distance(self):
        """Distance should decrease (or stay equal) across iterations."""
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.simulate_loop import run_loop  # type: ignore

        bench_stats = analyze((SAMPLE_FORMAL + "\n") * 4)
        result = run_loop(TARGET_DRAFT, bench_stats, max_iter=8, threshold=0.15)

        distances = [h["distance"] for h in result["history"]]
        self.assertGreater(len(distances), 1, "loop should run more than 0 iterations")
        for prev, cur in zip(distances, distances[1:]):
            self.assertLessEqual(cur, prev + 0.001,
                                 f"distance increased: {prev:.4f} -> {cur:.4f}")
        self.assertLess(distances[-1], distances[0],
                        "loop must reduce distance overall")

    def test_simulator_monotonic_across_seeds(self):
        """Property: distance must not increase across iterations for any seed.

        Catches the str.replace substring-collision bug (now fixed with
        sentence-boundary-anchored splicing).
        """
        import random
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.simulate_loop import run_loop  # type: ignore

        bench_stats = analyze((SAMPLE_FORMAL + "\n") * 4)
        for seed in [0, 1, 7, 17, 42, 123]:
            random.seed(seed)
            result = run_loop(TARGET_DRAFT, bench_stats, max_iter=6, threshold=0.15)
            distances = [h["distance"] for h in result["history"]]
            for prev, cur in zip(distances, distances[1:]):
                self.assertLessEqual(
                    cur, prev + 0.001,
                    f"seed={seed}: distance increased {prev:.4f} -> {cur:.4f}",
                )

    def test_simulator_halts_gracefully(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.simulate_loop import run_loop  # type: ignore

        bench_stats = analyze((SAMPLE_FORMAL + "\n") * 4)
        result = run_loop(TARGET_DRAFT, bench_stats, max_iter=8, threshold=0.15)
        self.assertIn(result["stop_reason"],
                      {"converged", "plateau", "max_iter",
                       "no_applicable_rule_changed_text"})


if __name__ == "__main__":
    unittest.main()
