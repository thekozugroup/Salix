"""Fresh installation and extracted release checks in isolated user homes."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.package_files import package_files  # noqa: E402


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="salix test ")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.project = self.home / "Project with spaces"
        self.project.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("SALIX_")}
        self.env["HOME"] = str(self.home)
        self.codex = self.home / ".agents/skills/salix"
        self.claude = self.home / ".claude/skills/salix"

    def run_command(self, *args, input=None, expected=0):
        result = subprocess.run(args, env=self.env, cwd=self.project, input=input,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def install(self, *args, expected=0):
        return self.run_command("bash", str(ROOT / "install.sh"), *args, expected=expected)

    def test_fresh_copies_are_independent_and_complete(self):
        self.install()
        for folder in (self.codex, self.claude):
            self.assertFalse(folder.is_symlink())
            self.assertTrue((folder / "scripts/stamatatos_baseline.py").is_file())
            self.assertTrue((folder / "references/rewriting.md").is_file())
            result = self.run_command(sys.executable, str(folder / "salix"), "doctor", "--json")
            self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertFalse((self.home / ".salix").exists())
        self.assertFalse((self.project / ".salix").exists())

    def test_upgrade_and_uninstall_preserve_external_profiles(self):
        store = self.home / ".salix/benchmarks"
        store.mkdir(parents=True)
        private = store / "voice.json"
        private.write_text("private profile bytes")
        self.install()
        self.install()
        self.install("--uninstall")
        self.assertEqual(private.read_text(), "private profile bytes")
        self.assertFalse(self.codex.exists())
        self.assertFalse(self.claude.exists())
        self.install("--uninstall")

    def test_unmanaged_collision_preflight_and_force_backup(self):
        self.claude.mkdir(parents=True)
        (self.claude / "mine.txt").write_text("keep me")
        self.install(expected=1)
        self.assertFalse(self.codex.exists())
        self.install("--force")
        backups = list(self.claude.parent.glob("salix.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "mine.txt").read_text(), "keep me")

    def test_uninstall_refuses_unmanaged_even_with_force(self):
        self.codex.mkdir(parents=True)
        (self.codex / "mine.txt").write_text("keep me")
        self.install("--codex", "--force", "--uninstall", expected=1)
        self.assertTrue((self.codex / "mine.txt").exists())

    def test_project_install_from_different_directory(self):
        other = self.home / "Other project"
        self.install("--codex", "--project", "--project-dir", str(other))
        self.assertTrue((other / ".agents/skills/salix/SKILL.md").is_file())
        self.assertFalse(self.codex.exists())
        self.assertFalse((other / ".salix").exists())

    def test_legacy_style_data_survives_update_and_blocks_uninstall(self):
        self.install("--codex")
        private = self.codex / "samples/essay.md"
        private.write_text("private sample")
        self.install("--codex")
        self.assertEqual(private.read_text(), "private sample")
        self.install("--codex", "--uninstall", expected=1)
        self.assertTrue(private.exists())
        self.install("--codex", "--link", expected=1)
        self.assertTrue(private.exists())

    def test_developer_link_uninstall_leaves_checkout(self):
        self.install("--codex", "--link")
        self.assertTrue(self.codex.is_symlink())
        self.install("--codex", "--uninstall")
        self.assertTrue((ROOT / "SKILL.md").exists())

    def test_unknown_private_files_block_update_and_uninstall(self):
        self.install("--codex")
        private = self.codex / "draft.md"
        private.write_text("private writing")
        sample = self.codex / "samples/legacy.md"
        sample.write_text("legacy style sample")
        config = self.codex / "config.json"
        config.write_text('{"hooks_enabled":true}')
        self.install("--codex", expected=1)
        self.install("--codex", "--uninstall", "--force", expected=1)
        self.assertEqual(private.read_text(), "private writing")
        self.install("--codex", "--force")
        backup = next(self.codex.parent.glob("salix.backup-*"))
        self.assertEqual((backup / "draft.md").read_text(), "private writing")
        self.assertEqual(sample.read_text(), "legacy style sample")
        self.assertEqual(json.loads(config.read_text()), {"hooks_enabled": True})

    def test_package_rejects_external_reference_symlinks(self):
        source = self.home / "source"
        for name in package_files(ROOT):
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        private = self.home / "secret.md"
        private.write_text("private writing")
        (source / "references/leak.md").symlink_to(private)
        with self.assertRaisesRegex(ValueError, "without symlinks"):
            package_files(source)

    def test_checkout_inside_destination_cannot_be_relocated(self):
        source = self.codex / "checkout"
        for name in [*package_files(ROOT), "scripts/install.py"]:
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        result = self.run_command(sys.executable, str(source / "scripts/install.py"),
                                  "--codex", "--force", "--link", expected=1)
        self.assertIn("containing the source checkout", result.stderr)
        self.assertFalse(self.codex.is_symlink())
        self.assertTrue((source / "salix").exists())

    def test_remote_copy_survives_temporary_download_cleanup(self):
        archive_path = self.home / "source.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name in [*package_files(ROOT), "scripts/install.py"]:
                archive.write(ROOT / name, f"Salix-main/{name}")
        binaries = self.home / "bin"
        binaries.mkdir()
        curl = binaries / "curl"
        curl.write_text('#!/usr/bin/env bash\nwhile [[ "$#" -gt 0 ]]; do\n'
                        '  if [[ "$1" == "-o" ]]; then destination="$2"; break; fi\n'
                        '  shift\ndone\ncp "$SALIX_TEST_ARCHIVE" "$destination"\n')
        curl.chmod(0o755)
        self.env["PATH"] = str(binaries) + os.pathsep + self.env["PATH"]
        self.env["SALIX_TEST_ARCHIVE"] = str(archive_path)
        self.env["TMPDIR"] = str(self.home)
        self.run_command("bash", input=(ROOT / "install.sh").read_text())
        self.assertTrue(self.codex.is_dir())
        self.assertFalse(list(self.home.glob("tmp.*/Salix-main")))
        self.assertTrue(json.loads(self.run_command(
            sys.executable, str(self.codex / "salix"), "doctor", "--json").stdout)["ok"])

    def test_remote_wrapper_rejects_temporary_link(self):
        script = self.home / "downloaded-install.sh"
        script.write_text((ROOT / "install.sh").read_text())
        result = self.run_command("bash", str(script), "--link", expected=1)
        self.assertIn("requires a local checkout", result.stderr)

    def test_release_archives_deterministic_and_runtime_works(self):
        out = self.home / "release/Salix.skill"
        args = (sys.executable, str(ROOT / "scripts/build_skill_bundle.py"),
                "--release", "--all", "--out", str(out))
        self.run_command(*args)
        before = out.read_bytes()
        self.run_command(*args)
        self.assertEqual(before, out.read_bytes())
        self.assertEqual(before, (out.parent / "Salix.zip").read_bytes())
        for line in (out.parent / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ")
            self.assertEqual(digest, hashlib.sha256((out.parent / name).read_bytes()).hexdigest())
        with zipfile.ZipFile(out) as archive:
            self.assertIsNone(archive.testzip())
            self.assertFalse(any("__pycache__" in name or "tests/" in name for name in archive.namelist()))
            self.assertEqual(archive.getinfo("salix/salix").external_attr >> 16 & 0o777, 0o755)
            archive.extractall(self.home / "extracted")
        cli = self.home / "extracted/salix/salix"
        self.assertTrue(json.loads(self.run_command(sys.executable, str(cli), "doctor", "--json").stdout)["ok"])
        corpus = self.home / "corpus"
        for name in ("one", "two"):
            (corpus / name).mkdir(parents=True)
            for index in range(3):
                (corpus / name / f"{index}.txt").write_text(f"The {name} author writes here. " * 20)
        self.run_command(sys.executable, str(cli), "baseline", "--corpus-dir", str(corpus))
        with zipfile.ZipFile(out.parent / "Salix-plugin.zip") as archive:
            for path in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
                         "hooks/hooks.json", "scripts/session_hook.py", "skills/salix/SKILL.md"):
                self.assertIn(f"salix/{path}", archive.namelist())
        for platform in ("codex", "claude"):
            folder = self.home / f"{platform}-extracted"
            with zipfile.ZipFile(out.parent / f"Salix.{platform}-plugin.zip") as archive:
                archive.extractall(folder)
            cli = folder / "salix/skills/salix/salix"
            self.assertTrue(json.loads(self.run_command(
                sys.executable, str(cli), "doctor", "--json").stdout)["ok"])
            self.env["SALIX_HOOKS"] = "1"
            hook = cli.parent / "scripts/session_hook.py"
            event = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.project)})
            context = json.loads(self.run_command(sys.executable, str(hook), input=event).stdout)
            self.assertEqual(context["hookSpecificOutput"]["hookEventName"], "SessionStart")


if __name__ == "__main__":
    unittest.main()
