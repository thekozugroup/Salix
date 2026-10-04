"""CLI diagnostics, scope, malformed-profile handling, and inert hooks."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "The writer observes the room, and perhaps considers the result. " * 40


class CLIHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="salix health ")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.project = self.home / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("SALIX_")}
        self.env["HOME"] = str(self.home)
        self.draft = self.project / "draft.md"
        self.draft.write_text(SAMPLE)

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(ROOT / "salix"), *args],
                                cwd=self.project, env=self.env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def hook(self, event, expected=0):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/session_hook.py")],
                                cwd=self.project, env=self.env, input=event,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result.stdout

    def setup_profile(self):
        samples = self.home / "samples"
        samples.mkdir()
        (samples / "essay.txt").write_text(SAMPLE)
        self.cli("setup", "--scope", "global", "--samples", str(samples))
        return self.home / ".salix/benchmarks/default.json"

    def test_diagnostics_read_only_without_profile(self):
        status = json.loads(self.cli("status", "--json").stdout)
        doctor = json.loads(self.cli("doctor", "--json").stdout)
        self.assertTrue(doctor["ok"])
        self.assertEqual(status["scope"], "global")
        self.assertFalse((self.home / ".salix").exists())

    def test_first_run_commands_have_absolute_cli_and_store(self):
        result = self.cli("init", "--scope", "project")
        line = next(line for line in result.stdout.splitlines() if "2. Run:" in line)
        command = shlex.split(line.split("2. Run: ")[1])
        self.assertEqual(command[1], str(ROOT / "salix"))
        self.assertEqual(command[-2], "--home")
        self.assertEqual(command[-1], str((self.project / ".salix").resolve()))

    def test_same_named_auto_fallback_reports_selected_store(self):
        self.setup_profile()
        self.cli("init", "--scope", "project")
        report = json.loads(self.cli("compare", str(self.draft), "--json").stdout)
        self.assertEqual(report["scope"], "global")
        self.assertEqual(report["profile_home"], str((self.home / ".salix").resolve()))
        self.cli("compare", str(self.draft), "--scope", "project", expected=1)

    def test_corrupt_profiles_have_actionable_errors_and_doctor_fails(self):
        path = self.setup_profile()
        original = json.loads(path.read_text())
        cases = [[], {"stats": []}, {"schema_version": True, "stats": {"ttr": 1}},
                 {"schema_version": 2, "stats": {"ttr": "bad"}},
                 {"schema_version": 2, "stats": {"ttr": float("nan")}},
                 {"schema_version": 2, "stats": {"ttr": 0.5, "_sigma": []}},
                 {"schema_version": 2, "stats": {"ttr": 1e308}},
                 {"schema_version": 2, "stats": {"ttr": 0.5, "mfw_top150": [["the", 1e308]]}},
                 {"schema_version": 2, "stats": {"ttr": 1.2}},
                 {"schema_version": 2, "stats": {"ttr": 0.5, "char_3grams": [["abc", "bad"]]}},
                 {"schema_version": 2, "stats": {"ttr": 0.5, "_sigma": {"ttr": -1}}}]
        for value in cases:
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                failed = self.cli("compare", str(self.draft), "--json", expected=2)
                self.assertNotIn("Traceback", failed.stderr)
                doctor = json.loads(self.cli("doctor", "--json", expected=1).stdout)
                self.assertFalse(doctor["ok"])
        path.write_text(json.dumps(original))

    def test_profile_depth_and_size_fail_without_tracebacks(self):
        path = self.setup_profile()
        for raw in ("[" * 1500 + "0" + "]" * 1500, " " * (8 * 1024 * 1024 + 1)):
            path.write_text(raw)
            result = self.cli("compare", str(self.draft), "--json", expected=2)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(json.loads(self.cli("doctor", "--json", expected=1).stdout)["ok"])

    def test_verbose_simulator_preserves_json_stdout(self):
        self.setup_profile()
        result = self.cli("simulate", str(self.draft), "--json", "--verbose", "--max-iter", "1")
        self.assertIn("history", json.loads(result.stdout))

    def test_hook_inert_until_enabled_and_uses_project_context(self):
        event = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.project)})
        self.assertEqual(self.hook(event), "")
        result = json.loads(self.cli("hooks", "enable", "--scope", "project").stdout)
        self.assertTrue(result["effective_enabled"])
        context = json.loads(self.hook(event))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("project store", context)
        self.assertTrue((self.project / ".salix/.gitignore").exists())
        self.env["SALIX_HOOKS"] = "0"
        self.assertEqual(self.hook(event), "")
        result = json.loads(self.cli("hooks", "status", "--scope", "project").stdout)
        self.assertTrue(result["hooks_enabled"])
        self.assertFalse(result["effective_enabled"])

    def test_hook_rejects_unexpected_event_and_preserves_config(self):
        self.cli("hooks", "enable", "--scope", "global")
        config = self.home / ".salix/config.json"
        data = json.loads(config.read_text())
        data["custom"] = "keep"
        config.write_text(json.dumps(data))
        self.cli("hooks", "disable", "--scope", "global")
        self.assertEqual(json.loads(config.read_text())["custom"], "keep")
        for event in ("not json", "[]", '{"hook_event_name":"Stop"}',
                      '{"hook_event_name":"SessionStart","cwd":"/missing/path"}'):
            self.assertEqual(self.hook(event), "")

    def test_hook_stays_inert_for_deep_json_invalid_scope_and_disabled_env(self):
        self.cli("hooks", "enable", "--scope", "global")
        config = self.home / ".salix/config.json"
        event = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.project)})
        for raw in ("[" * 1500 + "0" + "]" * 1500, " " * 65537):
            config.write_text(raw)
            self.assertEqual(self.hook(event), "")
            self.cli("hooks", "status", "--scope", "global", expected=2)
        self.env["SALIX_SCOPE"] = "not-a-scope"
        self.assertEqual(self.hook(event), "")
        self.env["SALIX_HOOKS"] = "0"
        self.assertEqual(self.hook("[" * 1500 + "0" + "]" * 1500), "")
        self.assertEqual(self.hook(event), "")


if __name__ == "__main__":
    unittest.main()
