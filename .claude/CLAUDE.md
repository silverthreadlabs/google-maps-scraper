# Auto-Pipeline Mode

When I give you a task that involves code changes (new features, refactors, bug fixes, migrations), execute it as a full pipeline WITHOUT stopping between phases. Do NOT ask "should I proceed?" — just proceed.

**Do NOT use the pipeline for:** simple questions, one-liner fixes, typos, explanations, discussions, or when I say "no pipeline" or "just do it".

## ECC Integration

Use ECC **skills and commands** throughout — they run in the current context and preserve all knowledge from previous phases. Do NOT use subagents unless parallel work on independent modules is needed.

## Pipeline Phases

Execute in order. **SKIP irrelevant phases** — print: `⏭ Phase X: [name] — skipped (reason)` and move on.

---

### Phase 1: Analyze & Plan
**Use:** `everything-claude-code:plan`, `everything-claude-code:search-first`, `everything-claude-code:architect` (for complex/ambiguous tasks)

- For complex, ambiguous, or cross-cutting tasks: use the `architect` agent/skill to design the system before coding — evaluate tradeoffs, define boundaries, and produce an architecture brief
- Search the codebase for ALL affected files (grep, glob, read)
- Apply `everything-claude-code:search-first` — look for existing solutions, patterns, utilities before planning custom work
- Restate requirements clearly
- Identify: affected files, edge cases, risks, dependencies on other modules
- Check existing project structure, patterns (naming, error handling, validation), and dependencies
- **Output:** Print a structured brief:
  ```
  📋 ANALYSIS
  Task: [one-line summary]
  Affected files: [list]
  Risks: [list or "none"]
  Existing patterns to follow: [what you found]
  Files to create/modify: [list]
  Approach: [2-3 sentences]
  ```
- → CONTINUE (do NOT wait for confirmation)

**SKIP if:** task is explicitly trivial (user said "just do it")

---

### Phase 2: Database Changes
**Use:** `everything-claude-code:database-migrations`, `everything-claude-code:postgres-patterns` (if PostgreSQL)

- Follow existing migration tool/ORM conventions per `everything-claude-code:database-migrations`
- Create migration files with proper up/down
- Add indexes if new query patterns require them
- Verify migration runs: execute migration command if safe to do so in dev

**SKIP if:** task has no database impact

---

### Phase 3: Tests (TDD — write BEFORE implementation)
**Use:** `everything-claude-code:tdd-workflow`

- Write failing tests FIRST — define the expected behavior before any production code exists
- Use the existing test framework (check what's already in the project)
- Cover: happy path + error paths + boundary/guard paths (per global TDD rules)
- Every `try/catch`, `else` branch, and early-return guard gets a test in this phase — not deferred
- Run tests — confirm they FAIL (red). If a test passes before implementation, it's not testing anything
- Tests drive the implementation in the next phases; do not write stubs or partial implementations here

**SKIP if:** task is trivial (renaming, config change)

---

### Phase 4: Backend Implementation
**Use:** `everything-claude-code:backend-patterns`, `everything-claude-code:security-review`, `everything-claude-code:api-design`

- Make all backend changes — the goal is to turn red tests green
- Apply `everything-claude-code:security-review`: input validation, parameterized queries, auth checks
- Check existing utils/helpers before writing new ones
- Follow existing error handling patterns exactly
- Run tests after implementation — confirm they PASS (green)

**SKIP if:** task is frontend-only

---

### Phase 5: Frontend Implementation
**Use:** `everything-claude-code:frontend-patterns`, `everything-claude-code:coding-standards`, `everything-claude-code:browser-qa`

- Make all frontend changes — turn remaining red tests green
- Follow existing component patterns, styling approach, state management
- Reuse existing components before creating new ones
- Handle: loading states, error states, empty states
- Accessibility: semantic HTML, ARIA, keyboard navigation
- Run tests after implementation — confirm they PASS (green)
- **Verify visually with `browser-qa`:** after implementation, use the Playwright MCP tools to navigate the running app and confirm changes landed as expected — check the golden path, error states, and watch for regressions

**SKIP if:** task is backend-only

---

### Phase 6: QA & Security Verification
**Use:** `everything-claude-code:code-review`, `everything-claude-code:security-review`, `everything-claude-code:verification-loop`

**This phase MUST produce a verification report. NEVER SKIP.**

Step 1 — Run automated checks (detect the project's toolchain and execute):
- Lint, typecheck, test suite, build — run whichever exist in the project
- Use `everything-claude-code:verification-loop` to drive the cycle
- **E2E tests (if frontend changed):** use the `e2e-runner` agent to run or generate E2E tests for critical user journeys — covers auth flows, CRUD operations, and navigation. Prefer Playwright MCP tools; quarantine flaky tests with `test.fixme()`

Step 2 — Apply `everything-claude-code:code-review` standards to all changed files:
- CRITICAL: hardcoded credentials, SQL injection, XSS, path traversal, auth bypasses
- HIGH: missing error handling, unvalidated input, insecure defaults
- MEDIUM: code duplication, missing types, poor naming

Step 3 — Apply `everything-claude-code:security-review` if changes touch: auth, API endpoints, user input, payments, data access

Step 4 — Manual checks:
- console.logs / debug code left behind
- Hardcoded values that should be env vars
- Broken imports / unused imports
- Dead code introduced

Step 5 — Fix ALL issues found → re-run checks

**Output:** Print verification report (include only checks that apply to this project):
```
✅ VERIFICATION REPORT
Tests: ✅ X passed, 0 failed | ❌ X failed (fixed)
Lint/Types: ✅ passed | ❌ X issues (fixed) | ⏭ N/A
Build: ✅ passed | ❌ failed (fixed) | ⏭ N/A
Security: ✅ no issues | ⚠️ [list findings]
Manual review: ✅ clean | ⚠️ [list findings]
```

---

### Phase 7: Documentation
- Update relevant docs, README, API docs
- Add comments only for complex logic (WHY, not WHAT)
- Update CHANGELOG if project has one

---

### Phase 8: Summary
**NEVER SKIP.** Print final summary:

```
📊 PIPELINE COMPLETE
━━━━━━━━━━━━━━━━━━━━
Task: [one-line summary]
Phases executed: [list, e.g., 1,3,4,6,8]
Phases skipped: [list with reasons]

Files modified: [count]
Files created: [count]
Files deleted: [count]

Tests: [X passed, X failed]
Security issues: [count or "none"]

Key decisions:
- [any architectural choices or tradeoffs made]
- [any assumptions noted]

⚠️ Needs human attention:
- [anything that requires manual verification, e.g., "test the modal on mobile"]
- [or "none — all automated checks passed"]
```
---

### Phase 9: Git & PR (after human confirms)

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
- Stage relevant files by name (never `git add -A` — review what's being staged)
- Use the `conventional-commits` skill to write the commit message
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
- **Check existing dependencies BEFORE adding new ones** — if something similar exists, USE IT
- **Search-first** — search codebase for existing tools, libs, patterns before writing custom code
- **Adapt to the codebase** — follow existing patterns, naming conventions, folder structure
- **Immutability** — create new objects, don't mutate
- **Small files** — 200-400 lines typical, 800 max
- **Performance** — avoid N+1 queries, paginate lists, use efficient solutions
- **No debug leftovers** — no console.logs, no commented-out code, no TODOs unless asked
- **When in doubt** — make the safe choice, note it in the summary
- **Every phase that runs MUST produce visible output** — no silent phases