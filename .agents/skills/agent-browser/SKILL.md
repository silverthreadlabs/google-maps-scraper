---
name: agent-browser
description: Browser automation with the agent-browser CLI. Use when Codex needs to open websites, interact with pages, fill forms, click controls, take screenshots, scrape visible page data, test web apps, log in with browser state, inspect network traffic, capture PDFs, or automate browser workflows.
---

# Browser Automation With agent-browser

This is the Codex port of `.claude/skills/agent-browser/SKILL.md`. The Claude frontmatter allowed tools were `Bash(npx agent-browser:*)` and `Bash(agent-browser:*)`; in Codex, use the shell normally with `agent-browser` or `npx agent-browser` when needed.

Use the `agent-browser` CLI for browser work that is better handled by a real Chromium session than by plain HTTP requests. It talks to Chrome/Chromium through CDP and can reuse browser state across commands.

## Install And Setup

Use an existing install when available:

```bash
agent-browser --help
```

If it is missing, install with one of:

```bash
npm i -g agent-browser
brew install agent-browser
cargo install agent-browser
agent-browser install
```

Installing packages or downloading Chrome may require user approval when network access is restricted.

## Core Workflow

1. Navigate: `agent-browser open <url>`.
2. Wait: `agent-browser wait --load networkidle` or wait for a specific selector/text.
3. Snapshot: `agent-browser snapshot -i`.
4. Interact with refs from the latest snapshot, such as `@e1`.
5. Re-snapshot after navigation, DOM changes, modals, or validation errors.

Example:

```bash
agent-browser open https://example.com/form
agent-browser wait --load networkidle
agent-browser snapshot -i
agent-browser fill @e1 "user@example.com"
agent-browser click @e2
agent-browser wait --load networkidle
agent-browser snapshot -i
```

Refs are snapshot-scoped. Refresh them before relying on an element after the page changes.

## Command Reference

Common commands:

```bash
agent-browser open <url>
agent-browser close
agent-browser snapshot -i
agent-browser click @e1
agent-browser fill @e2 "text"
agent-browser type @e2 "text"
agent-browser select @e1 "Option"
agent-browser check @e1
agent-browser press Enter
agent-browser scroll down 500
agent-browser get text @e1
agent-browser get url
agent-browser wait @e1
agent-browser wait --text "Welcome"
agent-browser wait "#spinner" --state hidden
agent-browser screenshot --full
agent-browser screenshot --annotate
agent-browser pdf output.pdf
agent-browser network requests
agent-browser network request <requestId>
```

Read `references/commands.md` for the full CLI command surface.

## Authenticated Sessions

Pick the lightest safe option:

- One-off reuse of the user's logged-in browser: `agent-browser --auto-connect state save ./auth.json`.
- Recurring local profile: `agent-browser --profile ~/.myapp open https://app.example.com/login`.
- Named session: `agent-browser --session-name myapp open https://app.example.com/login`.
- Manual state file: `agent-browser state save ./auth.json` and later `agent-browser state load ./auth.json`.

State files contain session tokens. Keep them out of git, remove them when no longer needed, and use `AGENT_BROWSER_ENCRYPTION_KEY` when encryption at rest is required. Read `references/authentication.md` and `references/session-management.md` for OAuth, 2FA, cookie refresh, and persistent-session patterns.

## Batches And Dependencies

The Claude source calls this section "Batch Execution" and also documents command chaining with `&&`. In this Codex repo, prefer separate shell calls when intermediate output must be inspected, and batch/chained calls when the sequence is known.

Use separate commands when output from one step determines the next action, especially `snapshot -i` followed by ref-based interactions.

Use `batch --json` for known sequences that do not depend on intermediate output:

```bash
printf '%s\n' '[["open","https://example.com"],["wait","--load","networkidle"],["screenshot","result.png"]]' | agent-browser batch --json
```

## References And Templates

- `references/snapshot-refs.md`: ref stability, scoping, and re-snapshot rules.
- `references/proxy-support.md`: proxy configuration and troubleshooting.
- `references/profiling.md`: performance and tracing.
- `references/video-recording.md`: recording workflows.
- `templates/authenticated-session.sh`: reusable auth-state flow.
- `templates/capture-workflow.sh`: screenshot/PDF capture pattern.
- `templates/form-automation.sh`: form automation pattern.
