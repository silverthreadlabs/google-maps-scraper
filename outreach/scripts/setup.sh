#!/usr/bin/env bash
#
# Bootstrap + verify the outreach pipeline prerequisites.
#
# Installs what is safe to install automatically:
#   - Python venv (outreach/.venv) + requirements.txt
#   - agent-browser CLI (via npm, global)
#   - Playwright browser binaries (via `agent-browser install`)
#
# Verifies (cannot be safely auto-installed here) and prints guidance:
#   - Node / npm        (prerequisite of agent-browser)
#   - Docker            (distro-specific, needs root + daemon)
#   - Claude Code       (the classify stage runs inside it)
#
# Usage:
#   outreach/scripts/setup.sh            # install + verify (idempotent)
#   outreach/scripts/setup.sh --check    # verify only, install nothing
#   outreach/scripts/setup.sh --help
#
# Re-runnable: every step checks before acting, so running twice is a no-op
# for anything already in place.

set -euo pipefail

# --- locate the outreach dir relative to this script (no hardcoded paths) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTREACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$OUTREACH_DIR/.venv"
REQ_FILE="$OUTREACH_DIR/requirements.txt"

CHECK_ONLY=0
MISSING=0   # count of unmet hard requirements

# --- pretty output -----------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RST=$'\033[0m'
else
  BOLD=''; GREEN=''; YELLOW=''; RED=''; DIM=''; RST=''
fi
ok()    { printf '%s✓%s %s\n'  "$GREEN"  "$RST" "$1"; }
warn()  { printf '%s!%s %s\n'  "$YELLOW" "$RST" "$1"; }
fail()  { printf '%s✗%s %s\n'  "$RED"    "$RST" "$1"; MISSING=$((MISSING+1)); }
step()  { printf '\n%s== %s ==%s\n' "$BOLD" "$1" "$RST"; }
note()  { printf '   %s%s%s\n' "$DIM" "$1" "$RST"; }

usage() {
  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) usage ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# pick a python interpreter
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

# detect the system package manager. agent-browser's `--with-deps` only knows
# apt-get/dnf/yum; on anything else (pacman, zypper, …) we install the browser
# binaries without it and print the system libs to install by hand.
PKG_MGR=""
for pm in apt-get dnf yum pacman zypper; do
  if command -v "$pm" >/dev/null 2>&1; then PKG_MGR="$pm"; break; fi
done
# pacman package names for the libs Chromium/Playwright needs to launch
PACMAN_DEPS="nss nspr atk at-spi2-core at-spi2-atk cups libdrm dbus libxcb \
libxkbcommon libx11 libxcomposite libxdamage libxext libxfixes libxrandr \
mesa expat alsa-lib pango cairo"

# =============================================================================
# 1. Python venv + dependencies  (auto-installable)
# =============================================================================
step "Python venv + dependencies"
if [ -z "$PY" ]; then
  fail "Python not found. Install Python 3.11+ and re-run."
else
  ok "$("$PY" --version 2>&1)"
  if [ ! -d "$VENV_DIR" ]; then
    if [ "$CHECK_ONLY" -eq 1 ]; then
      warn "venv missing at $VENV_DIR (run without --check to create it)"
    else
      note "creating venv at $VENV_DIR"
      "$PY" -m venv "$VENV_DIR"
      ok "venv created"
    fi
  else
    ok "venv present at $VENV_DIR"
  fi

  if [ -d "$VENV_DIR" ]; then
    VENV_PY="$VENV_DIR/bin/python"
    if [ "$CHECK_ONLY" -eq 1 ]; then
      # report whether declared deps import cleanly
      if "$VENV_PY" -c "import whois, bs4, yaml" >/dev/null 2>&1; then
        ok "Python deps importable (python-whois, beautifulsoup4, PyYAML)"
      else
        warn "Python deps not all importable (run without --check to install)"
      fi
    else
      note "installing $REQ_FILE into venv"
      "$VENV_PY" -m pip install --quiet --upgrade pip
      "$VENV_PY" -m pip install --quiet -r "$REQ_FILE"
      ok "Python deps installed"
    fi
  fi
fi

# =============================================================================
# 2. Node / npm  (verify-only — prerequisite of agent-browser)
# =============================================================================
step "Node / npm"
HAVE_NPM=0
if command -v npm >/dev/null 2>&1; then
  HAVE_NPM=1
  ok "npm $(npm --version 2>/dev/null)  |  node $(node --version 2>/dev/null || echo '?')"
else
  fail "npm not found. Install Node.js (https://nodejs.org or nvm) — required for agent-browser."
fi

# =============================================================================
# 3. agent-browser CLI  (auto-installable via npm)
# =============================================================================
step "agent-browser"
if command -v agent-browser >/dev/null 2>&1; then
  ok "agent-browser present ($(agent-browser --version 2>/dev/null || echo 'version?'))"
elif [ "$HAVE_NPM" -eq 1 ] && [ "$CHECK_ONLY" -eq 0 ]; then
  note "installing agent-browser globally via npm"
  npm install -g agent-browser
  ok "agent-browser installed"
elif [ "$HAVE_NPM" -eq 1 ]; then
  warn "agent-browser missing (run without --check to: npm install -g agent-browser)"
else
  fail "agent-browser missing and npm unavailable to install it."
fi

# =============================================================================
# 4. Playwright browser binaries  (auto-installable via agent-browser)
# =============================================================================
step "Playwright browser binaries"
# `--with-deps` also installs system libs, but only supports apt-get/dnf/yum.
# On those distros we use it; elsewhere (pacman, zypper, …) we install the
# browser binaries plain and tell the user which system libs to add by hand.
case "$PKG_MGR" in
  apt-get|dnf|yum) WITH_DEPS=1 ;;
  *)               WITH_DEPS=0 ;;
esac

if ! command -v agent-browser >/dev/null 2>&1; then
  warn "agent-browser not available yet — install it first, then: agent-browser install"
elif [ "$CHECK_ONLY" -eq 1 ]; then
  note "skipping browser install in --check mode"
  if [ "$WITH_DEPS" -eq 1 ]; then
    note "to (re)install: agent-browser install --with-deps"
  else
    note "to (re)install: agent-browser install   (then add system libs — see below)"
  fi
elif [ "$WITH_DEPS" -eq 1 ]; then
  note "installing browsers + system deps via 'agent-browser install --with-deps' ($PKG_MGR)"
  if agent-browser install --with-deps; then
    ok "browser binaries + system deps installed"
  else
    warn "browser install reported an issue — re-run 'agent-browser install --with-deps' manually"
  fi
else
  note "installing browser binaries via 'agent-browser install' (no --with-deps — $PKG_MGR not supported by it)"
  if agent-browser install; then
    ok "browser binaries installed"
  else
    warn "browser install reported an issue — re-run 'agent-browser install' manually"
  fi
  if [ "$PKG_MGR" = "pacman" ]; then
    warn "On Arch, install Chromium's system libs yourself if the browser fails to launch:"
    note "sudo pacman -S --needed $PACMAN_DEPS"
  elif [ -n "$PKG_MGR" ]; then
    warn "agent-browser can't auto-install system libs for '$PKG_MGR'."
    note "If the browser fails to launch, install Chromium/Playwright's libs via your package manager."
  else
    warn "No package manager detected — install Chromium's system libs manually if the browser fails to launch."
  fi
fi

# =============================================================================
# 5. Docker  (verify-only — distro-specific, needs root + daemon)
# =============================================================================
step "Docker (scrape stage)"
if command -v docker >/dev/null 2>&1; then
  ok "docker present ($(docker --version 2>/dev/null))"
  if docker info >/dev/null 2>&1; then
    ok "docker daemon reachable"
  else
    warn "docker installed but daemon not reachable (start it / check permissions)"
  fi
else
  fail "docker not found. Install Docker Engine — required for the scrape stage. https://docs.docker.com/engine/install/"
fi

# =============================================================================
# 6. Claude Code  (verify-only — runs the classify stage)
# =============================================================================
step "Claude Code (classify stage)"
if command -v claude >/dev/null 2>&1; then
  ok "claude CLI present ($(claude --version 2>/dev/null || echo 'version?'))"
else
  warn "claude CLI not on PATH. The classify stage runs the pain-classifier subagent inside Claude Code."
  note "install: https://claude.com/claude-code"
fi

# =============================================================================
# summary
# =============================================================================
step "Summary"
if [ "$MISSING" -eq 0 ]; then
  ok "All hard requirements satisfied."
  note "Activate the venv with:  source outreach/.venv/bin/activate"
  exit 0
else
  fail "$MISSING hard requirement(s) unmet — see ✗ lines above."
  exit 1
fi
