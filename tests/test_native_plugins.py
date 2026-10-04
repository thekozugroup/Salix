"""Optional installed-host integration; never touches the real user's settings."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("SALIX_TEST_NATIVE_HOSTS") == "1", "Opt-in installed-host checks")
class NativePluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="salix-native-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = os.environ.copy()
        self.env.update(HOME=str(self.home), CODEX_HOME=str(self.home / ".codex"),
                        CLAUDE_CONFIG_DIR=str(self.home / ".claude"))
        (self.home / ".codex").mkdir()

    def command(self, executable, *args):
        binary = shutil.which(executable)
        if not binary:
            self.skipTest(f"{executable} not installed")
        result = subprocess.run([binary, *args], cwd=ROOT, env=self.env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_codex_marketplace_and_plugin_install(self):
        self.command("codex", "plugin", "marketplace", "add", str(ROOT), "--json")
        result = self.command("codex", "plugin", "add", "salix@kozu-writing", "--json")
        self.assertIsInstance(json.loads(result.stdout), dict)
        self.command("codex", "plugin", "list", "--json")
        manifests = list((self.home / ".codex").rglob(".codex-plugin/plugin.json"))
        self.assertTrue(manifests, "Native plugin cache missing")

    def test_claude_plugin_and_marketplace_manifests(self):
        self.command("claude", "plugin", "validate", str(ROOT / ".claude-plugin/plugin.json"))
        self.command("claude", "plugin", "validate", str(ROOT / ".claude-plugin/marketplace.json"))
        self.command("claude", "plugin", "marketplace", "add", str(ROOT))
        self.command("claude", "plugin", "install", "salix@kozu-writing")


if __name__ == "__main__":
    unittest.main()
