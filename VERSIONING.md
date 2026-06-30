# Versioning Policy

Gemba Flow follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## Version Format

```
MAJOR.MINOR.PATCH
```

| Increment | When | Example |
|-----------|------|---------|
| **Patch** | Bug fixes, typo corrections, non-functional changes | Agent prompt fix, script bug fix, docs correction |
| **Minor** | New capabilities that are backward-compatible | New agent, new slash command, new workflow, new script |
| **Major** | Breaking changes that require user migration | Renamed/removed agents, restructured directories, changed bootstrap flow |

## Compatibility Promise

- **Patch** releases are always safe to adopt.
- **Minor** releases are additive — existing agent definitions, commands, and scripts continue to work without modification.
- **Major** releases may require migration. A migration guide will be included in the release notes and in `CHANGELOG.md`.

## What Constitutes a Breaking Change

- Renaming or removing an agent definition
- Changing the expected directory structure (`.claude/`, `docs/`, `scripts/`)
- Modifying `bootstrap.sh` in a way that changes required inputs
- Removing or renaming slash commands
- Changing CI workflow file names or trigger conditions that downstream forks depend on

## Release Process

1. All changes land on `main` via pull request.
2. When ready to release, a maintainer creates an annotated tag (`git tag -a vX.Y.Z`).
3. Pushing the tag triggers the GitHub Release workflow, which publishes a release with the relevant `CHANGELOG.md` section.

## Current Version

See the latest [GitHub Release](https://github.com/vibeacademy/gembaflow/releases) or the top entry in [CHANGELOG.md](./CHANGELOG.md).
