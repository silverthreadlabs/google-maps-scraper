# Auto-Pipeline Mode

When I give you a task that involves code changes (new features, refactors, bug fixes, migrations), execute it as a full pipeline WITHOUT stopping between phases. Do NOT ask "should I proceed?" — just proceed.

**Do NOT use the pipeline for:** simple questions, one-liner fixes, typos, explanations, discussions, or when I say "no pipeline" or "just do it".

## ECC Integration

Use ECC **skills and commands** throughout — they run in the current context and preserve all knowledge from previous phases. Do NOT use subagents unless parallel work on independent modules is needed.

## Pipeline Phases

Execute in order. **SKIP irrelevant phases** — print: `⏭ Phase X: [name] — skipped (reason)` and move on.

---

### Phase 1: Analyze & Plan
**Use:** `/plan` command principles + `search-first` skill

- Search the codebase for ALL affected files (grep, glob, read)
- Apply `search-first` — look for existing solutions, patterns, utilities before planning custom work
- Restate requirements clearly
- Identify: affected files, edge cases, risks, dependencies on other modules
- Check: does similar functionality already exist in the codebase?
- **Output:** Print a structured brief:
  ```
  📋 ANALYSIS
  Task: [one-line summary]
  Affected files: [list]
  Risks: [list or "none"]
  Existing patterns to follow: [what you found]
  Approach: [2-3 sentences]
  ```
- → CONTINUE (do NOT wait for confirmation)

**SKIP if:** task is explicitly trivial (user said "just do it")

---

### Phase 2: Codebase Scan & Architecture
**Use:** `coding-standards` skill, `backend-patterns` skill, `frontend-patterns` skill

- Check project structure (monorepo? folders? separate repos?)
- Read `package.json` (root + workspaces if monorepo) — note existing dependencies
- Identify existing patterns: routing, naming, state management, ORM, error handling, validation, auth
- **Dependency check:** List packages relevant to this task already in `package.json`
- Design solution that FOLLOWS existing conventions per `coding-standards` skill
- **Output:** Print the plan:
  ```
  🏗️ ARCHITECTURE
  Structure: [monorepo/single-repo/etc]
  Relevant existing deps: [list from package.json]
  Patterns to follow: [naming, routing, etc]
  Files to create: [list or "none"]
  Files to modify: [list]
  New dependencies needed: [list or "none — using existing X"]
  ```
- → CONTINUE

**SKIP if:** task is a simple fix (typo, config change, one-liner)

---

### Phase 3: Database Changes
**Use:** `database-migrations` skill, `postgres-patterns` skill (if PostgreSQL)

- Follow existing migration tool/ORM conventions per `database-migrations` skill
- Create migration files with proper up/down
- Add indexes if new query patterns require them
- Verify migration runs: execute migration command if safe to do so in dev

**SKIP if:** task has no database impact

---

### Phase 4: Backend Implementation
**Use:** `backend-patterns` skill, `security-review` skill, `api-design` skill

- Make all backend changes following `backend-patterns` skill
- Apply `security-review` skill: input validation, parameterized queries, auth checks
- Apply `api-design` skill for new/changed endpoints: proper status codes, error responses, pagination
- NEVER add a new dependency if `package.json` already has something similar
- Check existing utils/helpers before writing new ones
- Follow existing error handling patterns exactly

**SKIP if:** task is frontend-only

---

### Phase 5: Frontend Implementation
**Use:** `frontend-patterns` skill, `coding-standards` skill

- Make all frontend changes following `frontend-patterns` skill
- Follow existing component patterns, styling approach, state management
- Reuse existing components before creating new ones
- Handle: loading states, error states, empty states
- Accessibility: semantic HTML, ARIA, keyboard navigation

**SKIP if:** task is backend-only

---

### Phase 6: Tests
**Use:** `tdd-workflow` skill, `/tdd` command principles

- Apply `tdd-workflow` skill standards
- Use the existing test framework (check what's already in the project)
- Write tests: happy path + edge cases + error paths
- Descriptive names: "should [expected] when [condition]"
- **Actually run tests:** execute the test command (e.g., `npm test`, `pnpm test`, `yarn test`)
- Fix any failures
- Check coverage if thresholds exist

**SKIP if:** task is trivial (renaming, config change)

---

### Phase 7: QA & Security Verification
**Use:** `/code-review` command, `security-review` skill, `verification-loop` skill

**This phase MUST produce a verification report. NEVER SKIP.**

Step 1 — Run automated checks (actually execute these):
```bash
# Run ALL that exist in the project — skip any that don't
npm run lint          # or equivalent
npm run typecheck     # or tsc --noEmit
npm run test          # full suite
npm run build         # verify build passes
```

Step 2 — Apply `/code-review` standards to all changed files:
- CRITICAL: hardcoded credentials, SQL injection, XSS, path traversal, auth bypasses
- HIGH: missing error handling, unvalidated input, insecure defaults
- MEDIUM: code duplication, missing types, poor naming

Step 3 — Apply `security-review` skill if changes touch: auth, API endpoints, user input, payments, data access

Step 4 — Manual checks:
- console.logs / debug code left behind
- Hardcoded values that should be env vars
- Broken imports / unused imports
- Dead code introduced

Step 5 — Fix ALL issues found → re-run checks

**Output:** Print verification report:
```
✅ VERIFICATION REPORT
Lint: ✅ passed | ❌ X issues (fixed)
Types: ✅ passed | ❌ X errors (fixed)
Tests: ✅ X passed, 0 failed | ❌ X failed (fixed)
Build: ✅ passed | ❌ failed (fixed)
Security: ✅ no issues | ⚠️ [list findings]
Manual review: ✅ clean | ⚠️ [list findings]
```

---

### Phase 8: Documentation
- Update relevant docs, README, API docs
- Add JSDoc/comments only for complex logic (WHY, not WHAT)
- Update CHANGELOG if project has one

---

### Phase 9: Summary
**NEVER SKIP.** Print final summary:

```
📊 PIPELINE COMPLETE
━━━━━━━━━━━━━━━━━━━━
Task: [one-line summary]
Phases executed: [list, e.g., 1,2,4,6,7,9]
Phases skipped: [list with reasons]

Files modified: [count]
Files created: [count]
Files deleted: [count]

Tests: [X passed, X failed]
Lint: [pass/fail]
Types: [pass/fail]
Build: [pass/fail]
Security issues: [count or "none"]

Key decisions:
- [any architectural choices or tradeoffs made]
- [any assumptions noted]

⚠️ Needs human attention:
- [anything that requires manual verification, e.g., "test the modal on mobile"]
- [or "none — all automated checks passed"]
```
---

### Phase 10: Git & PR (after human confirms)

**PAUSE HERE.** Print:
```
🔀 Ready to push. Type "push" or "ship it" to proceed.
   Or type "changes" to review git diff first.
```

**Wait for human confirmation.** Only proceed when user says "push", "ship it", "go", "yes", or similar.

Once confirmed:

**Step 1 — Branch:**
- Generate branch name from task: `[type]/[short-description]`
  - Types: `feat/`, `fix/`, `refactor/`, `chore/`, `docs/`
  - Example: `refactor/remove-super-admin-routes`
- Check if branch exists, if so append a short suffix
- `git checkout -b [branch-name]`

**Step 2 — Commit:**
- Stage all changes: `git add -A`
- Write a commit message following conventional commits:
  ```
  [type]: [what was done]

  Why: [1-2 sentences explaining why this branch exists]
  
  Changes:
  - [grouped summary of what changed]
  
  Pipeline: phases [X,X,X] executed, [X,X] skipped
  ```
- `git commit`

**Step 3 — Push:**
- `git push`

- **Output:**
  ```
  ✅ PR CREATED (DRAFT)
  Branch: [branch-name]
  PR: [URL]
  Status: Draft — waiting for human review
  
  Next: Review the PR, then mark as "Ready for review" when satisfied.
  ```

**NEVER open a PR as ready for review. Always draft.**
**NEVER push without human confirmation.**

---

## Global Rules

- **SECURITY FIRST** — validate inputs, parameterize queries, check auth on every endpoint
- **Check `package.json` BEFORE installing ANY dependency** — if something similar exists, USE IT
- **Search-first** — search codebase for existing tools, libs, patterns before writing custom code
- **Adapt to the codebase** — follow existing patterns, naming conventions, folder structure
- **Immutability** — create new objects, don't mutate
- **Small files** — 200-400 lines typical, 800 max
- **Performance** — avoid N+1 queries, paginate lists, use efficient solutions
- **No debug leftovers** — no console.logs, no commented-out code, no TODOs unless asked
- **When in doubt** — make the safe choice, note it in the summary
- **Every phase that runs MUST produce visible output** — no silent phases