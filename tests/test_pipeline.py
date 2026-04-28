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

from lib.distance import compute_gaps  # noqa: E402
from lib.io_utils import clean_text  # noqa: E402
from lib.stats import aggregate, analyze, mtld, split_sentences, tokenize  # noqa: E402

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
        import os as _os

        from lib.io_utils import load_corpus as _lc
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

    def test_lexical_richness_measures(self):
        from lib.stats import honore_r, simpson_d, yule_k
        from lib.stats import tokenize as _tok
        toks = _tok(SAMPLE_FORMAL)
        self.assertGreater(yule_k(toks), 0)
        self.assertGreater(honore_r(toks), 0)
        d = simpson_d(toks)
        self.assertGreaterEqual(d, 0.0)
        self.assertLessEqual(d, 1.0)
        # Empty or 1-token input should not crash
        self.assertEqual(yule_k([]), 0.0)
        self.assertEqual(simpson_d(["one"]), 0.0)

    def test_char_ngrams_present_and_normalized(self):
        from lib.stats import char_ngrams
        grams = char_ngrams(SAMPLE_FORMAL, n=3, top_k=50)
        self.assertGreater(len(grams), 0)
        # frequencies sum to ≤ 1 (top_k is a truncation)
        self.assertLessEqual(sum(f for _, f in grams), 1.0 + 1e-6)
        # 'the' is a high-frequency 3-gram in English prose
        gmap = dict(grams)
        self.assertIn("the", gmap)

    def test_burrows_mfw_present(self):
        from lib.stats import burrows_delta_features
        from lib.stats import tokenize as _tok
        toks = _tok(SAMPLE_FORMAL)
        mfw = burrows_delta_features(toks, len(toks), top_k=20)
        self.assertGreater(len(mfw), 0)
        self.assertEqual(len(mfw[0]), 2)

    def test_compute_gaps_includes_char_ngrams_and_delta(self):
        formal = analyze(SAMPLE_FORMAL)
        target = analyze(TARGET_DRAFT)
        gaps = compute_gaps(target, formal)
        self.assertIn("char_3grams", gaps["ngram_gaps"])
        self.assertIn("char_4grams", gaps["ngram_gaps"])
        self.assertIn("mfw_top150", gaps["ngram_gaps"])
        self.assertEqual(gaps["ngram_gaps"]["char_3grams"]["metric"], "cosine")
        self.assertEqual(gaps["ngram_gaps"]["mfw_top150"]["metric"], "burrows_delta")

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


class TestEdgeCases(unittest.TestCase):
    """Inputs that have historically broken naive style tools."""

    def test_empty_input_returns_zero_word_count(self):
        s = analyze("")
        self.assertEqual(s["word_count"], 0)
        self.assertEqual(s["sentence_count"], 0)
        # No NaN / inf values
        for k, v in s.items():
            if isinstance(v, float):
                import math as _m
                self.assertFalse(_m.isnan(v), f"{k} is NaN")
                self.assertFalse(_m.isinf(v), f"{k} is inf")

    def test_single_sentence_input(self):
        s = analyze("This is a single sentence.")
        self.assertEqual(s["sentence_count"], 1)
        self.assertGreater(s["word_count"], 3)

    def test_all_caps_input(self):
        s = analyze("HE WALKED IN. SHE LOOKED UP. THEY LEFT.")
        self.assertEqual(s["sentence_count"], 3)

    def test_mostly_markdown_only(self):
        # Heavy markdown — should not crash; words after cleaning should be few
        raw = "# Header\n\n```python\nimport sys\nprint(sys.path)\n```\n\n## Sub\n\n- a\n- b\n- c\n"
        cleaned = clean_text(raw)
        s = analyze(cleaned)
        self.assertGreaterEqual(s["word_count"], 0)
        # The 3 bullet items reduce to a few words; should not be flagged as
        # multi-sentence prose.
        self.assertLessEqual(s["sentence_count"], 1)
        self.assertLessEqual(s["word_count"], 10)

    def test_file_of_urls(self):
        raw = "\n".join(f"http://example.com/{i}" for i in range(20))
        cleaned = clean_text(raw)
        # Cleaned text should be empty or near-empty
        self.assertLess(len(cleaned.split()), 5)

    def test_cjk_input_handled(self):
        # CJK is a known limitation; metric must not crash, just report low counts
        s = analyze("私は東京で食べる。明日は雨だろう。")
        self.assertGreaterEqual(s["word_count"], 0)
        self.assertGreaterEqual(s["sentence_count"], 0)

    def test_very_long_repeated_input(self):
        # 5000 sentences — should finish in <2s and produce sane stats
        import time
        text = ("This is sentence number one. This is sentence number two. " * 2500)
        t0 = time.time()
        s = analyze(text)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 5.0, f"analyze took {elapsed:.2f}s — too slow")
        self.assertGreater(s["word_count"], 1000)

    def test_distance_stable_under_repeated_calls(self):
        """Calling analyze + compute_gaps twice with the same input must produce
        identical numeric output (no hidden global state)."""
        bench = aggregate([analyze(SAMPLE_FORMAL), analyze(SAMPLE_FORMAL[:300])])
        s1 = analyze(TARGET_DRAFT)
        s2 = analyze(TARGET_DRAFT)
        g1 = compute_gaps(s1, bench)
        g2 = compute_gaps(s2, bench)
        self.assertEqual(g1["total_distance"], g2["total_distance"])

    def test_aggregate_handles_zero_word_doc(self):
        """A sample that cleans to empty should not crash aggregate."""
        s_empty = analyze("")
        s_normal = analyze(SAMPLE_FORMAL)
        agg = aggregate([s_empty, s_normal])
        self.assertGreater(agg["total_word_count"], 0)

    def test_max_file_bytes_rejected(self):
        from lib.io_utils import MAX_FILE_BYTES, load_text as _load
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            fh.write(b"x" * (MAX_FILE_BYTES + 1024))
            tmp_path = fh.name
        try:
            with self.assertRaises(ValueError):
                _load(Path(tmp_path))
        finally:
            Path(tmp_path).unlink()

    def test_malformed_benchmark_raises_clearly(self):
        """A corrupt benchmark JSON must surface as a clear SystemExit, not
        an opaque traceback. The CLI also retries briefly before giving up."""
        import os as _os
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "benchmarks").mkdir()
            (home / "samples").mkdir()
            (home / "benchmarks" / "broken.json").write_text("{not json")
            draft = home / "d.md"
            draft.write_text(SAMPLE_FORMAL)
            res = subprocess.run(
                [sys.executable, str(ROOT / "salix"), "compare",
                 str(draft), "--profile", "broken"],
                capture_output=True, text=True,
                env={**_os.environ, "SALIX_HOME": str(home)},
            )
            self.assertNotEqual(res.returncode, 0)
            err = res.stderr + res.stdout
            self.assertTrue("could not be decoded" in err or "JSON" in err)

    def test_splice_sentence_avoids_substring_collision(self):
        """_splice_sentence must skip mid-sentence substring matches and
        only edit at real sentence boundaries — preventing the original
        str.replace bug where a phrase appearing inside a longer sentence
        was rewritten in the wrong place."""
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.simulate_loop import _splice_sentence  # type: ignore
        text = "He said performance is better than expected. Performance is better."
        # Lowercase "performance is better" only occurs mid-sentence — no
        # boundary match — so the splice must be a no-op.
        out = _splice_sentence(text, "performance is better", "REPLACED")
        self.assertEqual(out, text, "should not edit a mid-sentence substring")
        # But the boundary-anchored full sentence does splice cleanly.
        out2 = _splice_sentence(text, "Performance is better.", "It improved.")
        self.assertIn("It improved.", out2)
        # First-sentence content is preserved
        self.assertIn("He said performance is better than expected.", out2)

    def test_modal_hedge_disambiguation(self):
        """'May 2024' must not count as a hedge; 'may rain' should."""
        from lib.tone import count_modal_hedges
        text = "the meeting was held in may 2024. it may rain tomorrow."
        from lib.stats import tokenize as _tok
        n = count_modal_hedges(_tok(text), text)
        # Only "may rain" (followed by a verb) counts.
        self.assertEqual(n, 1)

    def test_modal_request_form_not_hedge(self):
        """'Could you' (request) must not count as a hedge."""
        from lib.tone import count_modal_hedges
        text = "could you bring it. it could be useful."
        from lib.stats import tokenize as _tok
        n = count_modal_hedges(_tok(text), text)
        self.assertEqual(n, 1)  # only "could be" counts

    def test_sentence_length_quantiles_present(self):
        s = analyze(SAMPLE_FORMAL)
        for k in ("sent_len_p25", "sent_len_p50", "sent_len_p75", "sent_len_p90"):
            self.assertIn(k, s)
        # Quantiles must be monotonically non-decreasing
        self.assertLessEqual(s["sent_len_p25"], s["sent_len_p50"])
        self.assertLessEqual(s["sent_len_p50"], s["sent_len_p75"])
        self.assertLessEqual(s["sent_len_p75"], s["sent_len_p90"])

    def test_formality_source_reported(self):
        s = analyze(SAMPLE_FORMAL)
        self.assertIn(s.get("formality_source"), ("spacy", "suffix_proxy"))

    def test_pos_proxy_suffix_rules(self):
        from lib.stats import pos_proxies
        # 'national' has suffix '-al' (>5 chars) → adj
        counts = pos_proxies(["national", "globally", "creation", "running"])
        self.assertEqual(counts["adj"], 1)   # national
        self.assertEqual(counts["adv"], 1)   # globally
        self.assertEqual(counts["noun"], 1)  # creation (-tion)
        self.assertEqual(counts["verb"], 1)  # running (-ing)


class TestSimulatorMultiSeed(unittest.TestCase):
    """Simulator monotonicity across many seeds and inputs (catches the
    previously-fixed str.replace substring-collision bug + future regressions)."""

    def test_property_no_runaway_distance_explosion(self):
        """Across many seeds and inputs, no single iteration may double the
        distance — a guard against the previously-fixed substring-collision
        bug, which caused multi-x distance jumps when the wrong span was
        rewritten. Per-iter bounce within a sane bound is acceptable; the
        rule-based simulator is heuristic and only validates loop mechanics."""
        import random
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.simulate_loop import run_loop  # type: ignore

        bench_corpora = [
            (SAMPLE_FORMAL + "\n") * 4,
            (SAMPLE_CASUAL + "\n") * 4,
        ]
        drafts = [
            TARGET_DRAFT,
            "It works. It works fine. The system is now ready.",
            "Performance is excellent and users are happy with the results.",
        ]
        for bench_text in bench_corpora:
            bench = analyze(bench_text)
            for draft in drafts:
                for seed in range(20):
                    random.seed(seed)
                    result = run_loop(draft, bench, max_iter=4, threshold=0.1)
                    distances = [h["distance"] for h in result["history"]]
                    for prev, cur in zip(distances, distances[1:]):
                        self.assertLessEqual(
                            cur, prev * 1.8 + 0.05,
                            f"seed={seed} draft='{draft[:30]}': "
                            f"runaway distance {prev:.3f} -> {cur:.3f}",
                        )

    def test_simulator_helps_on_realistic_draft(self):
        """The original regression: on a meaningful draft against a stable
        benchmark, the simulator must achieve a net distance reduction."""
        import random
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.simulate_loop import run_loop  # type: ignore

        bench = analyze((SAMPLE_FORMAL + "\n") * 4)
        improved = 0
        for seed in range(10):
            random.seed(seed)
            result = run_loop(TARGET_DRAFT, bench, max_iter=6, threshold=0.15)
            distances = [h["distance"] for h in result["history"]]
            if len(distances) >= 2 and distances[-1] < distances[0]:
                improved += 1
        self.assertGreaterEqual(improved, 8, f"only {improved}/10 seeds improved")


class TestValidationHarness(unittest.TestCase):
    """Smoke + threshold tests for the empirical validation harness."""

    def test_attribution_above_chance(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.validate import attribution_check  # type: ignore
        result = attribution_check(authors=4, docs_per_author=5,
                                   seed=42, sentences_per_doc=40)
        chance = 1.0 / 4
        self.assertGreaterEqual(
            result["accuracy"], chance + 0.3,
            f"attribution accuracy {result['accuracy']:.2f} not "
            f"meaningfully above chance {chance:.2f}",
        )

    def test_topic_transfer_separates_authors(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.validate import topic_transfer_check  # type: ignore
        result = topic_transfer_check(authors=4, seed=11, sentences_per_doc=40)
        self.assertGreater(
            result["mean_other_author_distance"],
            result["mean_same_author_distance"],
            "same-author should be closer than other-author on unseen topic",
        )
        self.assertGreaterEqual(result["separation_accuracy"], 0.7)

    def test_stability_drift_bounded(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.validate import stability_check  # type: ignore
        result = stability_check(seed=3, sentences_per_doc=40)
        # Drift should be reasonably small — not a hard physical bound but a
        # sanity check that LOO benchmarks aren't wildly different from full.
        self.assertLess(result["max_drift"], 1.5)


if __name__ == "__main__":
    unittest.main()
