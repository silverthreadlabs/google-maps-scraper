---
name: codex-development-pipeline
description: Full Codex development pipeline ported from CLAUDE.md. Use when the user asks for pipeline, auto-pipeline, full pipeline, or a structured end-to-end code change workflow using ECC skills and commands.
---

# Codex Development Pipeline

This is the Codex port of `.claude/CLAUDE.md` Auto-Pipeline Mode. Use Codex-visible skill names in this repo, with the original Claude/ECC names preserved in the mapping section below.

## Auto-Pipeline Mode

When the user gives a task that involves code changes such as new features, refactors, bug fixes, or migrations, execute it as a full pipeline without stopping between phases. Do not ask "should I proceed?" unless a phase explicitly requires human confirmation.

Do not use the pipeline for simple questions, one-line fixes, typos, explanations, discussions, or when the user says "no pipeline" or "just do it".

## ECC Integration

Use ECC skills and commands throughout. They run in the current context and preserve knowledge from previous phases.

Do not use subagents unless parallel work on independent modules is needed. In Codex, spawn subagents only when the user explicitly asks for subagents, delegation, or parallel agent work.

## Phase Handling

Execute phases in order. Skip irrelevant phases and print:

```text
Phase X: <name> - skipped (<reason>)
```

Every phase that runs must produce visible output.

## Phase 1: Analyze And Plan

Use:

- `plan`
- `search-first`
- `architect` for complex or ambiguous tasks

Codex notes:

- `plan` is a repo-local Codex skill shim for the ECC `/plan` command.
- `search-first` is an ECC skill installed under `~/.agents/skills`.
- `architect` is a repo-local Codex skill shim for the ECC `architect` agent.

Steps:

- For complex, ambiguous, or cross-cutting tasks, use the `architect` agent/skill to design the system before coding. Evaluate tradeoffs, define boundaries, and produce an architecture brief.
- Search the codebase for all affected files with fast search and targeted reads.
- Apply `search-first`: look for existing solutions, patterns, and utilities before planning custom work.
- Restate requirements clearly.
- Identify affected files, edge cases, risks, and dependencies on other modules.
- Check existing project structure, naming, error handling, validation, and dependencies.

Output:

```text
ANALYSIS
Task: <one-line summary>
Affected files: <list>
Risks: <list or "none">
Existing patterns to follow: <what you found>
Files to create/modify: <list>
Approach: <2-3 sentences>
```

Continue after this phase. Do not wait for confirmation.

Skip if the task is explicitly trivial or the user said "just do it".

## Phase 2: Database Changes

Use:

- `database-migrations`
- `postgres-patterns` if PostgreSQL

Steps:

- Follow existing migration tool and ORM conventions per `database-migrations`.
- Create migration files with proper up/down behavior where the project supports it.
- Add indexes if new query patterns require them.
- Verify the migration runs if safe in the local dev environment.

Skip if the task has no database impact.

## Phase 3: Tests

Use:

- `tdd-workflow`

Steps:

- Write failing tests first. Define expected behavior before production code exists.
- Use the existing test framework.
- Cover happy path, error paths, and boundary or guard paths.
- Every `try/catch`, `else` branch, and early-return guard gets a test in this phase, not deferred.
- Run tests and confirm they fail red. If a test passes before implementation, it is not testing the new behavior.
- Let tests drive implementation in later phases. Do not write stubs or partial production implementation in this phase.

Skip if the task is trivial, such as a rename or config-only change.

## Phase 4: Backend Implementation

Use:

- `backend-patterns`
- `security-review`
- `api-design`

Steps:

- Make backend changes with the goal of turning red tests green.
- Apply `security-review`: input validation, parameterized queries, and auth checks.
- Check existing utilities and helpers before writing new ones.
- Follow existing error handling patterns exactly.
- Run tests after implementation and confirm they pass green.

Skip if the task is frontend-only.

## Phase 5: Frontend Implementation

Use:

- `frontend-patterns`
- `coding-standards`
- `browser-qa`

Steps:

- Make frontend changes and turn remaining red tests green.
- Follow existing component patterns, styling approach, and state management.
- Reuse existing components before creating new ones.
- Handle loading states, error states, and empty states.
- Preserve accessibility: semantic HTML, ARIA, and keyboard navigation.
- Run tests after implementation and confirm they pass.
- Verify visually with `browser-qa`: after implementation, use Playwright MCP tools to navigate the running app and confirm changes landed as expected. Check golden path, error states, and regressions.

Skip if the task is backend-only.

## Phase 6: QA And Security Verification

Use:

- `code-review`
- `security-review`
- `verification-loop`

This phase must produce a verification report. Never skip it.

Step 1: Run automated checks.

- Detect the project's toolchain and execute applicable lint, typecheck, test suite, and build commands.
- Use `verification-loop` to drive the cycle.
- For frontend changes, use the `e2e-runner` agent to run or generate E2E tests for critical user journeys. Cover auth flows, CRUD operations, and navigation. Prefer Playwright MCP tools. Quarantine flaky tests with `test.fixme()`.

Step 2: Apply `code-review` standards to all changed files.

- Critical: hardcoded credentials, SQL injection, XSS, path traversal, auth bypasses.
- High: missing error handling, unvalidated input, insecure defaults.
- Medium: code duplication, missing types, poor naming.

Step 3: Apply `security-review` if changes touch auth, API endpoints, user input, payments, or data access.

Step 4: Manual checks.

- Console logs or debug code left behind.
- Hardcoded values that should be env vars.
- Broken imports or unused imports.
- Dead code introduced.

Step 5: Fix all issues found and re-run checks.

Output:

```text
VERIFICATION REPORT
Tests: <passed | failed and fixed | not run with reason>
Lint/Types: <passed | failed and fixed | not applicable>
Build: <passed | failed and fixed | not applicable>
Security: <no issues | findings>
Manual review: <clean | findings>
```

## Phase 7: Documentation

Steps:

- Update relevant docs, README, and API docs.
- Add comments only for complex logic, explaining why, not what.
- Update CHANGELOG if the project has one.

## Phase 8: Summary

Never skip this phase.

Output:

```text
PIPELINE COMPLETE
Task: <one-line summary>
Phases executed: <list, e.g. 1,3,4,6,8>
Phases skipped: <list with reasons>

Files modified: <count>
Files created: <count>
Files deleted: <count>

Tests: <passed/failed summary>
Security issues: <count or "none">

Key decisions:
- <architectural choices, tradeoffs, or assumptions>

Needs human attention:
- <manual verification needed, or "none">
```

## Phase 9: Git And PR

Pause here and print:

```text
Ready to push. Type "push" or "ship it" to proceed.
Or type "changes" to review git diff first.
```

Wait for human confirmation. Only proceed when the user says "push", "ship it", "go", "yes", or similar.

After confirmation:

1. Branch:
   - Generate a branch name from the task: `[type]/[short-description]`.
   - Types: `feat/`, `fix/`, `refactor/`, `chore/`, `docs/`.
   - Example: `refactor/remove-super-admin-routes`.
   - Check if the branch exists; if so, append a short suffix.
   - Run `git checkout -b <branch-name>`.

2. Commit:
   - Stage relevant files by name. Never use `git add -A`.
   - Use the `conventional-commits` skill to write the commit message.
   - Run `git commit`.

3. Push:
   - Run `git push`.
   - Open PRs as draft only.

Output:

```text
PR CREATED (DRAFT)
Branch: <branch-name>
PR: <url>
Status: Draft - waiting for human review

Next: Review the PR, then mark as "Ready for review" when satisfied.
```

Never open a PR as ready for review. Never push without human confirmation.

## Global Rules

- Security first: validate inputs, parameterize queries, and check auth on every endpoint.
- Check existing dependencies before adding new ones. If something similar exists, use it.
- Search first: search the codebase for existing tools, libraries, and patterns before writing custom code.
- Adapt to the codebase: follow existing patterns, naming conventions, and folder structure.
- Immutability: create new objects, do not mutate.
- Small files: 200-400 lines typical, 800 max.
- Performance: avoid N+1 queries, paginate lists, and use efficient solutions.
- No debug leftovers: no console logs, no commented-out code, and no TODOs unless asked.
- When in doubt, make the safe choice and note it in the summary.
- Every phase that runs must produce visible output. No silent phases.

## Claude-To-Codex Surface Mapping

The original `.claude/CLAUDE.md` referenced these Claude/ECC surfaces. Use the Codex-visible names in the right column:

| Original Claude/ECC name | Codex-visible surface |
|---|---|
| `everything-claude-code:plan` | `plan` |
| `everything-claude-code:search-first` | `search-first` |
| `everything-claude-code:architect` | `architect` |
| `everything-claude-code:database-migrations` | `database-migrations` |
| `everything-claude-code:postgres-patterns` | `postgres-patterns` |
| `everything-claude-code:tdd-workflow` | `tdd-workflow` |
| `everything-claude-code:backend-patterns` | `backend-patterns` |
| `everything-claude-code:security-review` | `security-review` |
| `everything-claude-code:api-design` | `api-design` |
| `everything-claude-code:frontend-patterns` | `frontend-patterns` |
| `everything-claude-code:coding-standards` | `coding-standards` |
| `everything-claude-code:browser-qa` | `browser-qa` |
| `everything-claude-code:code-review` | `code-review` |
| `everything-claude-code:verification-loop` | `verification-loop` |
| `e2e-runner` | `e2e-runner` |
| `conventional-commits` | `conventional-commits` |
