"""Shared allowlist for standalone skills, installs, and plugin archives."""

from pathlib import Path

RUNTIME_FILES = (
    "SKILL.md", "LICENSE", "salix", "lib/__init__.py", "lib/distance.py",
    "lib/function_words.py", "lib/io_utils.py", "lib/stats.py", "lib/tone.py", "lib/social.py",
    "lib/package_files.py", "scripts/_path.py", "scripts/analyze.py",
    "scripts/compare.py", "scripts/ingest.py", "scripts/simulate_loop.py",
    "scripts/validate.py", "scripts/stamatatos_baseline.py", "scripts/visualize.py",
    "references/setup.md", "references/rewriting.md", "references/validation.md", "references/social.md",
    "agents/openai.yaml",
    "benchmarks/.gitkeep", "samples/.gitkeep",
)
PLUGIN_FILES = (
    ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
    "skills/salix/SKILL.md", "hooks/hooks.json", "scripts/session_hook.py",
)


def package_files(root: Path, plugin: bool = False) -> list[str]:
    root = root.resolve()
    files = list(RUNTIME_FILES)
    for folder in ("references", "agents"):
        files.extend(str(path.relative_to(root)) for path in sorted((root / folder).rglob("*"))
                     if path.is_file() and path.suffix in {".md", ".yaml"})
    if plugin:
        files.extend(PLUGIN_FILES)
    files = list(dict.fromkeys(files))
    missing = [name for name in files if not (root / name).is_file()]
    if missing:
        raise ValueError("Missing package files: " + ", ".join(missing))
    for name in files:
        path = root / name
        if not path.resolve().is_relative_to(root) or any(
                part.is_symlink() for part in [path, *path.parents] if part != root and root in part.parents):
            raise ValueError(f"Package file must be inside the checkout without symlinks: {name}")
    return files
