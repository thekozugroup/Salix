# Using Salix

Salix learns measurable writing patterns from your samples and helps your
assistant refine a draft in that voice. The assistant makes the edits; Salix
provides comparisons. A lower score is useful feedback, not a guaranteed match.

## Ask Naturally

Once installed, use a personal-voice request:

- "Set up Salix for my personal writing voice."
- "Build my style profile from these writing samples."
- "Refresh my client-a profile with these samples."
- "Make this draft sound like me, keeping every fact and quote unchanged."
- "Compare this draft with my project voice; don't edit it."
- "Analyze the rhythm and formality of this text."
- "Diagnose why Salix cannot find my profile."

For explicit invocation, use `$salix` in Codex, `/salix` for a standalone Claude
Code skill, or `/salix:salix` for the Claude plugin. Follow it with the task.
Natural discovery depends on the host loading the skill; reload the host after
installation if it is not available.

## Install Once

Python 3.9+ is required. From a Salix checkout, install copied skills for both
Codex and Claude Code:

```bash
bash ./install.sh
```

Default destinations are `~/.agents/skills/salix` and
`~/.claude/skills/salix`. A copy does not depend on keeping the source checkout
in place. Installing the skill does not create a writing profile.

To install only in a chosen project or host:

```bash
bash ./install.sh --project --project-dir /absolute/path/to/project
bash ./install.sh --codex --global
bash ./install.sh --claude --global
```

`--link` is opt-in for a checkout-backed installation; keep that checkout
available. Use `bash ./install.sh --help` for current options. Removal with
`--uninstall` is for managed installed code, not personal writing data. Do not
remove profile stores or samples to uninstall a skill.

The plugin is an alternative to the standalone skill. Native manifests support
Claude Code and Codex; the Claude plugin command is `/salix:salix`, while Codex
uses `$salix`. Plugin installation and enablement use the host's plugin controls.

## Choose Your Voice

Installation location and writing-data location are separate choices:

- **Global profile:** your personal voice across projects, stored in
  `~/.salix` by default.
- **Project profile:** a client, team, or context-specific voice in the
  project's `.salix` directory.
- **Named profile:** `default`, `casual`, or `client-a` within the selected store.

Auto mode prefers a discovered project store containing `samples/` or
`benchmarks/`, otherwise global. A project store can win even before it has a
usable benchmark. For a command requesting a profile, auto can fall back to a
global profile with that same name when it is missing from the project. It
never chooses another name. If both stores contain `default`, specify which
you mean: "Use my global default voice" or "Use this project's client-a voice."

Plain status and an auto comparison can select different stores. Confirm the
comparison's `profile`, `profile_home`, and `scope`; if an older CLI lacks them, use an explicit
`--home` and matching `status --json --home`. The assistant should explain any
global fallback and keep the selected store fixed during your rewrite.

An explicit `--home` overrides `SALIX_HOME`; `SALIX_HOME` overrides scope.
`SALIX_SCOPE` sets the scope when no explicit scope is supplied.
`SALIX_GLOBAL_HOME` changes the global store. Check the actual selected store
before ingesting or rewriting.

## Direct Commands

Use the CLI beside the root `SKILL.md`, not a project-relative `./salix`.
Keep your project as the working directory. For a default global Codex install:

```bash
SALIX_CLI="$HOME/.agents/skills/salix/salix"
PROJECT_DIR="$PWD"
python3 "$SALIX_CLI" doctor --json --project-dir "$PROJECT_DIR"
python3 "$SALIX_CLI" status --json --project-dir "$PROJECT_DIR"
```

For Claude standalone, use `$HOME/.claude/skills/salix/salix`. For a project or
plugin install, resolve the absolute CLI next to the root instruction file.
Plugin `skills/salix` wrappers refer back to that root file. Do not change into
the installation directory to run it. `--project-dir` controls profile discovery;
it does not change relative document paths.

Choose one setup command:

```bash
python3 "$SALIX_CLI" init --scope global
# Or, for a project-specific voice:
python3 "$SALIX_CLI" init --scope project --project-dir "$PROJECT_DIR"
```

Collect your own `.txt` or `.md` writing samples. Prefer multiple independent
pieces from the relevant register. Around 3,000 total cleaned words, or 10,000+
when available, is guidance, not a guarantee. Individual samples below 300
cleaned words are skipped by default.
Match audience and format: a narrative profile is not automatically a good
target for emails or dialogue-heavy scenes. The current language heuristics
are English-focused; scores for other languages need separate validation.

After choosing the store and sample directory:

```bash
PROFILE_HOME="/absolute/path/to/chosen/.salix"
SAMPLE_DIR="/absolute/path/to/writing-samples"
DRAFT="/absolute/path/to/draft.md"
python3 "$SALIX_CLI" ingest --name default --samples "$SAMPLE_DIR" --home "$PROFILE_HOME"
python3 "$SALIX_CLI" benchmark --profile default --home "$PROFILE_HOME"
python3 "$SALIX_CLI" analyze "$DRAFT" --json --pretty
python3 "$SALIX_CLI" compare "$DRAFT" --profile default --home "$PROFILE_HOME" --json --pretty
```

For first-time setup with samples ready, this combines initialization and
profile building:

```bash
python3 "$SALIX_CLI" setup --name default --samples "$SAMPLE_DIR" --home "$PROFILE_HOME"
```

Ingest rebuilds the profile from the selected samples; it does not append to an
old benchmark. Keep all samples you intend to retain when refreshing.
`analyze` does not need a profile. There is no CLI rewrite command: ask the host
assistant to rewrite using the skill.

## What A Rewrite Delivers

The assistant preserves your original unless you explicitly request in-place
editing. It makes small passes, checks the raw text for facts and formatting,
and stops when safe improvements run out, progress plateaus, or the pass budget
is reached. The default host budget is six passes, not a promise of convergence.

Expect the output path, chosen profile/store, actual before/after distance,
pass count, stopping reason, and checks performed. Quotes, numbers, code, URLs,
and citations remain intact. A score reduction is not a "voice accuracy"
percentage; an unmeasured rewrite must be labeled unmeasured.

## Privacy And Hooks

Raw samples, profile metadata, text-derived fragments, drafts, and reports may
be sensitive. CLI analysis is local; the assistant/model's data handling is
separate. Keep writing data outside installed code and verify it is not tracked
before committing or sharing. Project `init` creates a local ignore file, but
it cannot protect already tracked data.

Plugin SessionStart hooks are opt-in via `SALIX_HOOKS=1` or `.salix/config.json`
containing `"hooks_enabled": true`; project configuration is preferred. Use
Salix to change saved settings for the intended scope:

```bash
python3 "$SALIX_CLI" hooks enable --scope project --project-dir "$PROJECT_DIR"
python3 "$SALIX_CLI" hooks disable --scope project --project-dir "$PROJECT_DIR"
```

Run only the action you intend. Hooks emit profile context, never automatic
document edits. Hook context is not consent to change your writing. Inspect
effective settings if an environment override and saved configuration disagree:
`hooks status` shows saved configuration, while `SALIX_HOOKS` can override it.

## Check The Evidence

Diagnostics show runtime/store readiness, not writing quality. Synthetic tests
and the rule-based simulator check mechanics, not real author accuracy or
meaning preservation. Use actual real writing and review the result before
claiming voice quality. No latency, accuracy, or convergence claim should be
inferred from installation success or an example chart.

Task-specific guidance: [setup and profiles](../references/setup.md),
[rewriting](../references/rewriting.md), and
[validation and reporting](../references/validation.md).
