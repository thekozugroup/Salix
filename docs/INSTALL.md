# Installation

Choose one installation method per agent to avoid duplicate skill listings.
Installation scope controls where the skill is discovered, not where your voice
profiles live. Python 3.9+ is required; the runtime has no mandatory packages.

## Standalone Skill

```bash
curl -fsSL https://raw.githubusercontent.com/thekozugroup/Salix/main/install.sh | bash
```

The script checks Python first, downloads the source with curl/unzip, then copies
only the skill runtime. It never changes agent settings or enables hooks.
Read the script before running it if your environment requires source review.
No administrator access is required. This shell installer supports macOS/Linux;
Windows users can use an upload bundle or run it through WSL.

| Target | Personal skill path | Project skill path |
| --- | --- | --- |
| Codex | `~/.agents/skills/salix/` | `<project>/.agents/skills/salix/` |
| Claude Code | `~/.claude/skills/salix/` | `<project>/.claude/skills/salix/` |

For one agent or a project:

```bash
curl -fsSL https://raw.githubusercontent.com/thekozugroup/Salix/main/install.sh | bash -s -- --codex
curl -fsSL https://raw.githubusercontent.com/thekozugroup/Salix/main/install.sh | bash -s -- --claude
curl -fsSL https://raw.githubusercontent.com/thekozugroup/Salix/main/install.sh | bash -s -- --project --project-dir "$PWD"
```

From a checkout: `./install.sh` uses the same copier. `--link` is an explicit
developer option and requires keeping that local checkout. A remote installation
rejects `--link` because its temporary source is removed after installation.

Open a new agent session. Trigger with `$salix` in Codex or `/salix` in Claude Code.
Your agent can also select the skill from a request such as "rewrite in my voice".
This depends on the host's skill selection; it is not guaranteed for every prompt.

## Native Plugins

Native plugins bundle the skill and an opt-in session hook. Standalone installation
is the simplest path; plugins are for users who prefer their host's plugin manager.
Plugin commands require a host version with plugin support.

Claude Code (user-wide by default):

```text
/plugin marketplace add thekozugroup/Salix
/plugin install salix@kozu-writing
```

Then use `/salix:salix`. For local development, load the repository using
`claude --plugin-dir /absolute/path/to/Salix`.
For only the current project, use `claude plugin install salix@kozu-writing --scope project`
from that project's directory instead of the default user installation.

Codex CLI (user-wide installation):

```bash
codex plugin marketplace add thekozugroup/Salix
codex plugin add salix@kozu-writing
```

For local development, pass the absolute checkout path to `marketplace add`.
Restart the session after installing. The plugin's skill is named `salix`.
The Codex app may also expose plugins through its Plugins interface.
For repository-specific enablement, review the project's `.codex/config.toml`:

```toml
[plugins."salix@kozu-writing"]
enabled = true
```

Set `enabled = false` to disable it in that trusted project. These settings
do not uninstall the plugin or change workspace-managed installation policies.
See [Codex project enablement](https://developers.openai.com/plugins/build/plugins#enable-or-disable-a-plugin-for-a-repo).

## Optional Session Context

Hooks are inert until enabled in the active style store. Ask your agent to run:

```bash
python3 /absolute/path/to/installed/salix hooks enable --scope global
python3 /absolute/path/to/installed/salix hooks status --scope global
python3 /absolute/path/to/installed/salix hooks disable --scope global
```

Use `--scope project --project-dir /path/to/project` for project-only preferences.
Native host hook trust/approval still applies. The hook adds a short profile
availability reminder; it does not read draft text, alter files, or call a model.
Standalone skills do not register hooks. `SALIX_HOOKS=0` disables the hook even
when a store has it enabled; `SALIX_HOOKS=1` is an explicit session override.

## Update And Remove

Rerun the installer to update a managed installation. Unmanaged folders are
refused unless you choose `--force`; then their entire contents are backed up
beside the installation before replacement. Check that backup before removing it.
Unknown files in a managed skill also block updates/removal. A forced update
retains the whole previous folder as a backup; it never discards unknown files.

```bash
./install.sh --uninstall
./install.sh --project --project-dir /path/to/project --uninstall
```

Uninstall removes only managed skill code. Global/project profiles remain.
If a copied installation contains legacy samples or profiles inside the skill
folder, updates preserve them and uninstall refuses until you move them out.
Plugin removal uses the host's plugin manager. Neither method removes profiles.

Without a checkout, remove standalone skills using:

```bash
curl -fsSL https://raw.githubusercontent.com/thekozugroup/Salix/main/install.sh | bash -s -- --uninstall
```

Add `--project --project-dir /path/to/project` for project-installed skills.

Older installs may remain in `~/.codex/skills/salix`. The installer does not delete
that legacy path automatically. Inspect it and remove only the old skill link/code
after moving any embedded profiles. Keep one discovered Salix per host/scope.

## Upload Bundles

```bash
python3 scripts/build_skill_bundle.py --release
```

The `.skill` and `.zip` archives have one `salix/` folder containing `SKILL.md`,
the runtime, and references. The plugin ZIP additionally contains both manifests,
the native skill wrapper, and hooks. Private samples, profiles, tests, and caches
are excluded. `SHA256SUMS` records the archive hashes; these are integrity checks,
not publisher signatures. Tagged releases publish all four assets.

In Claude's Skills settings, upload `Salix.zip` (or `.skill` if accepted) and enable
it. UI labels may differ by Claude version/account. Upload does not install a
local CLI or native hooks. Python/script execution must be available in the host.

## Verify

Run the installed CLI from your project, using its absolute path:

```bash
python3 ~/.agents/skills/salix/salix doctor --json
python3 ~/.agents/skills/salix/salix status --json
```

For Claude Code substitute `~/.claude/skills/salix/salix`. `doctor` returning
`ok: true` verifies the runtime and readable profiles, not host activation or
writing quality. No profile yet is an onboarding action, not an installation error.

Official host references: [Codex skills](https://developers.openai.com/codex/skills/),
[Codex plugins](https://developers.openai.com/plugins/build/plugins), and
[Claude Code plugins](https://code.claude.com/docs/en/plugins).
