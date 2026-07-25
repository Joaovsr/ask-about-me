
Check ./CONTEXT.md for terminology questions.

For user-facing changes, add a changeset to .changeset. Check all changesets there first to see if there are duplicates. We use @changesets/cli, but you can create/edit the file manually. Make all bugfixes patch, all new features or breaking changes minor (since we're pre-1.0). Use package.json#name for the name.

When changing public-facing behavior, check README.md to see if the documentation needs updating.

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues at `Joaovsr/ask-about-me`. External PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default canonical labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
