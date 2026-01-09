# Contributing to NEXUS STACK

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/) to automate versioning and changelog generation.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | New feature | **Minor** (0.1.0 → 0.2.0) |
| `fix` | Bug fix | **Patch** (0.1.0 → 0.1.1) |
| `refactor` | Code change (no new feature, no bug fix) | **Patch** |
| `perf` | Performance improvement | **Patch** |
| `docs` | Documentation only | **Patch** |
| `style` | Formatting, missing semicolons, etc. | **Patch** |
| `test` | Adding tests | **Patch** |
| `chore` | Maintenance tasks | **Patch** |
| `ci` | CI/CD changes | **Patch** |
| `build` | Build system changes | **Patch** |

### Breaking Changes

For breaking changes, add `!` after the type or include `BREAKING CHANGE:` in the footer:

```bash
# Option 1: With !
feat!: Remove deprecated API endpoints

# Option 2: In footer
feat: Restructure configuration format

BREAKING CHANGE: The nexus.tfvars format has changed.
```

Breaking changes trigger a **Major** version bump (0.1.0 → 1.0.0).

### Examples

```bash
# Feature (Minor bump)
feat: Add Airflow stack

# Feature with scope
feat(stacks): Add Apache Spark integration

# Bug fix (Patch bump)
fix: Correct Grafana port mapping

# Documentation
docs: Update installation instructions

# Refactoring
refactor: Simplify deploy script

# Breaking change (Major bump)
feat!: Change secret management to Vault-only
```

### Scopes (optional)

| Scope | Use for |
|-------|---------|
| `stacks` | Docker stack changes |
| `tofu` | OpenTofu/Infrastructure changes |
| `docs` | Documentation |
| `ci` | GitHub Actions / CI |
| `scripts` | Shell scripts |

---

## Release Process

Releases are created **automatically** when commits are pushed to `main`:

1. GitHub Action analyzes commits since last tag
2. Determines version bump based on commit types
3. Generates changelog
4. Creates GitHub Release with tag

**No manual tagging required!**

---

## Pull Request Workflow

1. Create a feature branch from `main`
2. Make changes with conventional commits
3. Open PR to `main`
4. After merge → Release is created automatically

```bash
# Example workflow
git checkout -b feat/add-airflow
# ... make changes ...
git commit -m "feat(stacks): Add Apache Airflow orchestrator"
git push origin feat/add-airflow
# Open PR, get review, merge
# → v0.X.0 release created automatically
```
