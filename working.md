# Salix Development Handoff

## Scope

- Easy self-contained skill installation and native Claude Code/Codex packaging.
- Separate personal/project voices, safe rewrites, clear setup and diagnostics.
- Cleaner README patterned after Platter; detailed documentation in docs/.
- Real measurements and honest chart provenance; no fabricated AI convergence.
- Keep Salix as the name, per the user's current decision.
- Commit/push as thekozugroup@gmail.com; no AI co-author tags.

## Current State

- Three specialist agents completed runtime, evidence, and skill documentation work.
- Parent integrated installer, package allowlist, manifests/hooks, CLI diagnostics,
  scope metadata, documentation, and integration tests.
- Full Python 3.11 suite: 151 tests, no failures, three optional skips.
- Both native plugin managers passed isolated-home local install checks.
- Ruff and shell syntax checks pass; release assets built locally in ignored dist/.
- Python 3.10 run and final independent reviews are being completed.
- Do not touch unrelated untracked .a5c/ files.

## Quality Gates

- Extracted runtime works independently; baseline helper and references included.
- Updates/removal preserve external profiles and refuse unknown or legacy data.
- Forced replacement keeps a recoverable previous-folder backup.
- Package inputs cannot escape through symlinks.
- JSON output remains parseable; final simulator scores match final text.
- Hooks are inert unless explicitly enabled and never alter documents.
- Evidence tests remeasure every recorded fixture text and reject false claims.

## Remaining Work

- Finish review, final tests, commit/push, and verify exact committed state.
- Publish release assets only after checks of the committed revision.
- Real AI comparison/convergence evidence remains missing. The checked-in
  50-step fixture copies training text and cannot fulfill that proof requirement.
- Claude app upload and in-session host skill selection need live user-host QA.
- Real spaCy/pyphen performance and Windows installation are not verified.
- Do not assign universal 100% grades or imply perfect writing fidelity.
