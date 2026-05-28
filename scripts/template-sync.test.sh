#!/usr/bin/env bash
# Regression test: template-sync must never overwrite itself at runtime.

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

pass() {
  echo -e "  ${GREEN}PASS${NC}: $1"
  TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
  echo -e "  ${RED}FAIL${NC}: $1"
  TESTS_FAILED=$((TESTS_FAILED + 1))
}

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
SCRIPT_SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPO_DIR="$WORK_DIR/repo"
mkdir -p "$REPO_DIR/scripts/lib"
cp scripts/template-sync.sh "$REPO_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$REPO_DIR/scripts/lib/overrides.sh"
chmod +x "$REPO_DIR/scripts/template-sync.sh"

cat > "$REPO_DIR/.gembaflow-version" <<'JSON'
{
  "version": "0.1.0",
  "syncDirectories": [
    "./scripts"
  ]
}
JSON

: > "$REPO_DIR/.gembaflow-overrides"

mkdir -p "$WORK_DIR/upstream/vibeacademy-agile-flow-release/scripts/lib"
cp scripts/template-sync.sh "$WORK_DIR/upstream/vibeacademy-agile-flow-release/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$WORK_DIR/upstream/vibeacademy-agile-flow-release/scripts/lib/overrides.sh"
echo "# upstream mutation" >> "$WORK_DIR/upstream/vibeacademy-agile-flow-release/scripts/template-sync.sh"

tar -czf "$WORK_DIR/upstream.tar.gz" -C "$WORK_DIR/upstream" vibeacademy-agile-flow-release

mkdir -p "$WORK_DIR/bin"
cat > "$WORK_DIR/bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"/releases/latest"* ]]; then
  printf '{"tag_name":"v1.0.0","html_url":"https://example.invalid/release","tarball_url":"https://example.invalid/upstream.tar.gz"}'
  exit 0
fi
if [[ "$*" == *"upstream.tar.gz"* ]]; then
  out=''
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  cp "$TEST_UPSTREAM_TARBALL" "$out"
  exit 0
fi
exit 1
SH
chmod +x "$WORK_DIR/bin/curl"

pushd "$REPO_DIR" >/dev/null
git init >/dev/null
git add .
git commit -m "init" >/dev/null
git init --bare "$WORK_DIR/origin.git" >/dev/null
git remote add origin "$WORK_DIR/origin.git"
git push -u origin HEAD >/dev/null

SCRIPT_BEFORE_SUM=$(sha256sum scripts/template-sync.sh | awk '{print $1}')

if TEST_UPSTREAM_TARBALL="$WORK_DIR/upstream.tar.gz" PATH="$WORK_DIR/bin:$PATH" bash scripts/template-sync.sh > "$WORK_DIR/run.log" 2>&1; then
  SCRIPT_AFTER_SUM=$(sha256sum scripts/template-sync.sh | awk '{print $1}')
  if [ "$SCRIPT_BEFORE_SUM" = "$SCRIPT_AFTER_SUM" ]; then
    pass "runtime-protected template-sync.sh is not overwritten"
  else
    fail "template-sync.sh changed despite runtime protection"
  fi

  if grep -q "SKIP (runtime-protected): scripts/template-sync.sh" "$WORK_DIR/run.log"; then
    pass "runtime-protected skip is reported"
  else
    fail "expected runtime-protected skip log entry"
  fi
else
  cat "$WORK_DIR/run.log"
  fail "template-sync.sh execution failed"
fi

popd >/dev/null

echo ""
echo "Scenario 2: bootstrap re-entry dirty state is allowed for sync-target paths"

REENTRY_DIR="$WORK_DIR/reentry"
mkdir -p "$REENTRY_DIR/scripts/lib"

cat > "$REENTRY_DIR/.gembaflow-version" <<'JSON'
{
  "version": "0.0.1",
  "syncDirectories": [
    "scripts"
  ]
}
JSON

cat > "$REENTRY_DIR/scripts/template-sync.sh" <<'SH'
#!/usr/bin/env bash
echo "legacy placeholder"
SH
chmod +x "$REENTRY_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$REENTRY_DIR/scripts/lib/overrides.sh"

mkdir -p "$WORK_DIR/reentry-upstream/scripts"
cp scripts/template-sync.sh "$WORK_DIR/reentry-upstream/scripts/template-sync.sh"
tar -czf "$WORK_DIR/reentry-upstream.tar.gz" -C "$WORK_DIR/reentry-upstream" .

cat > "$WORK_DIR/bin/curl-reentry" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"/releases/latest"* ]]; then
  printf '{"tag_name":"v1.0.4","html_url":"https://example.invalid/release","tarball_url":"https://example.invalid/reentry-upstream.tar.gz"}'
  exit 0
fi
if [[ "$*" == *"reentry-upstream.tar.gz"* ]]; then
  out=''
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  cp "$TEST_REENTRY_TARBALL" "$out"
  exit 0
fi
exit 1
SH
chmod +x "$WORK_DIR/bin/curl-reentry"

mkdir -p "$WORK_DIR/reentry-bin"
cp "$WORK_DIR/bin/curl-reentry" "$WORK_DIR/reentry-bin/curl"
chmod +x "$WORK_DIR/reentry-bin/curl"
cat > "$WORK_DIR/reentry-bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "gh $*" >> "$TEST_GH_LOG"
if [[ "${1:-}" == "pr" && "${2:-}" == "create" ]]; then
  echo "https://example.invalid/pr/204"
  exit 0
fi
if [[ "${1:-}" == "pr" && "${2:-}" == "list" ]]; then
  echo '[]'
  exit 0
fi
exit 0
SH
chmod +x "$WORK_DIR/reentry-bin/gh"

pushd "$REENTRY_DIR" >/dev/null
git init >/dev/null
git add .
git commit -m "init reentry" >/dev/null
git init --bare "$WORK_DIR/reentry-origin.git" >/dev/null
git remote add origin "$WORK_DIR/reentry-origin.git"
git push -u origin HEAD >/dev/null

cp "$SCRIPT_SOURCE_DIR/template-sync.sh" scripts/template-sync.sh
git add scripts/template-sync.sh .gembaflow-version

if TEST_REENTRY_TARBALL="$WORK_DIR/reentry-upstream.tar.gz" TEST_GH_LOG="$WORK_DIR/reentry-gh.log" PATH="$WORK_DIR/reentry-bin:$PATH" bash scripts/template-sync.sh > "$WORK_DIR/reentry.log" 2>&1; then
  pass "bootstrap re-entry run exits successfully"
  if grep -q "detected bootstrap re-entry" "$WORK_DIR/reentry.log"; then
    pass "bootstrap warning is emitted"
  else
    fail "expected bootstrap warning in re-entry run"
  fi

  DOWNLOAD_COUNT=$(grep -c "Downloading release tarball..." "$WORK_DIR/reentry.log" || true)
  if [ "$DOWNLOAD_COUNT" = "0" ]; then
    pass "no second-pass tarball download in re-entry path"
  else
    fail "expected no tarball download banner in re-entry path"
  fi

  if git show-ref --verify --quiet refs/heads/gembaflow-sync/v1.0.4; then
    pass "re-entry path creates local sync branch"
  else
    fail "expected local sync branch gembaflow-sync/v1.0.4"
  fi

  if git --git-dir "$WORK_DIR/reentry-origin.git" show-ref --verify --quiet refs/heads/gembaflow-sync/v1.0.4; then
    pass "re-entry path pushes sync branch to origin"
  else
    fail "expected sync branch pushed to origin"
  fi

  if grep -q "gh pr create" "$WORK_DIR/reentry-gh.log"; then
    pass "re-entry path opens PR"
  else
    fail "expected gh pr create call in re-entry path"
  fi
else
  cat "$WORK_DIR/reentry.log"
  fail "bootstrap re-entry scenario failed"
fi
popd >/dev/null

###############################################################################
# Scenario 3: configurable upstream + redirect-safe curl + 404 fallback (#331)
###############################################################################
# These scenarios exit early (before the tarball download) so they only need
# to verify which curl URL was hit for the /releases/latest call. We stub
# curl to record the URL and return a no-op JSON, and stub gh to satisfy the
# auth precondition.

UPSTREAM_DIR="$WORK_DIR/upstream-scenarios"
mkdir -p "$UPSTREAM_DIR/scripts/lib"
cp scripts/template-sync.sh "$UPSTREAM_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$UPSTREAM_DIR/scripts/lib/overrides.sh"
chmod +x "$UPSTREAM_DIR/scripts/template-sync.sh"

mkdir -p "$WORK_DIR/upstream-bin"
# Curl stub: log each releases/latest URL probed and respond per the test's
# scripted policy (env-driven). For tarball downloads, behave as a no-op.
cat > "$WORK_DIR/upstream-bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
url=""
for arg in "$@"; do
  case "$arg" in
    https://*|http://*) url="$arg" ;;
  esac
done
if [[ "$url" == *"/releases/latest"* ]]; then
  echo "$url" >> "$TEST_CURL_LOG"
  # Policy: if TEST_PRIMARY_REPO matches the URL, return 200 JSON; if
  # TEST_FALLBACK_REPO matches and primary was tried, return 200 JSON; else 404.
  if [[ -n "${TEST_404_REPOS:-}" ]] && [[ ",$TEST_404_REPOS," == *",$url,"* ]]; then
    exit 22  # curl's -f exit code for HTTP >= 400
  fi
  printf '{"tag_name":"v9.9.9","html_url":"https://example.invalid/r","tarball_url":"https://example.invalid/t.tar.gz"}'
  exit 0
fi
if [[ "$url" == *".tar.gz"* ]]; then
  out=''
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then out="$2"; shift 2; continue; fi
    shift
  done
  : > "$out"
  exit 0
fi
exit 1
SH
chmod +x "$WORK_DIR/upstream-bin/curl"

cat > "$WORK_DIR/upstream-bin/gh" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "auth" && "${2:-}" == "token" ]]; then echo "fake-token"; exit 0; fi
exit 0
SH
chmod +x "$WORK_DIR/upstream-bin/gh"

run_upstream_scenario() {
  local label="$1"
  local upstream_field="$2"
  local expected_first_repo="$3"  # owner/repo expected on the FIRST curl
  local fail_404_repos="$4"        # comma-joined list of full URLs to 404
  local scenario_dir="$WORK_DIR/scen-${label}"
  local curl_log="$WORK_DIR/curl-${label}.log"
  : > "$curl_log"

  mkdir -p "$scenario_dir/scripts/lib"
  cp scripts/template-sync.sh "$scenario_dir/scripts/template-sync.sh"
  cp scripts/lib/overrides.sh "$scenario_dir/scripts/lib/overrides.sh"
  chmod +x "$scenario_dir/scripts/template-sync.sh"
  : > "$scenario_dir/.gembaflow-overrides"

  if [ -n "$upstream_field" ]; then
    cat > "$scenario_dir/.gembaflow-version" <<JSON
{
  "version": "9.9.9",
  "upstream": "$upstream_field",
  "syncDirectories": ["./scripts"]
}
JSON
  else
    cat > "$scenario_dir/.gembaflow-version" <<'JSON'
{
  "version": "9.9.9",
  "syncDirectories": ["./scripts"]
}
JSON
  fi

  pushd "$scenario_dir" >/dev/null
  git init >/dev/null
  git add .
  git commit -m "init $label" >/dev/null
  # Run the script; since LOCAL_VERSION already matches the mock's v9.9.9,
  # the script exits 0 right after the version fetch — exactly what we want.
  TEST_CURL_LOG="$curl_log" \
    TEST_404_REPOS="$fail_404_repos" \
    PATH="$WORK_DIR/upstream-bin:$PATH" \
    bash scripts/template-sync.sh > "$WORK_DIR/scen-${label}.log" 2>&1 || true
  popd >/dev/null

  local first_url
  first_url=$(head -n1 "$curl_log" || true)
  if [[ "$first_url" == *"/repos/${expected_first_repo}/releases/latest" ]]; then
    pass "[${label}] first curl targets ${expected_first_repo}"
  else
    fail "[${label}] expected first curl to target ${expected_first_repo}, got: ${first_url:-<none>}"
  fi
}

# (a) upstream field honored when present
run_upstream_scenario "upstream-honored" "vibeacademy/example-variant" "vibeacademy/example-variant" ""

# (a2) upstream URL form normalized to owner/repo
run_upstream_scenario "upstream-url-normalized" "https://github.com/vibeacademy/example-variant" "vibeacademy/example-variant" ""

# (b) absent upstream falls back to hardcoded default
run_upstream_scenario "upstream-absent" "" "vibeacademy/gembaflow" ""

# (c) 404 from primary -> fallback URL is tried
FAIL_URL="https://api.github.com/repos/vibeacademy/gembaflow/releases/latest"
SCEN_DIR="$WORK_DIR/scen-fallback"
mkdir -p "$SCEN_DIR/scripts/lib"
cp scripts/template-sync.sh "$SCEN_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$SCEN_DIR/scripts/lib/overrides.sh"
chmod +x "$SCEN_DIR/scripts/template-sync.sh"
: > "$SCEN_DIR/.gembaflow-overrides"
cat > "$SCEN_DIR/.gembaflow-version" <<'JSON'
{
  "version": "9.9.9",
  "syncDirectories": ["./scripts"]
}
JSON
pushd "$SCEN_DIR" >/dev/null
git init >/dev/null
git add .
git commit -m "init fallback" >/dev/null
TEST_CURL_LOG="$WORK_DIR/curl-fallback.log" \
  TEST_404_REPOS="$FAIL_URL" \
  PATH="$WORK_DIR/upstream-bin:$PATH" \
  bash scripts/template-sync.sh > "$WORK_DIR/scen-fallback.log" 2>&1 || true
popd >/dev/null

URL1=$(sed -n '1p' "$WORK_DIR/curl-fallback.log" || true)
URL2=$(sed -n '2p' "$WORK_DIR/curl-fallback.log" || true)
if [[ "$URL1" == *"/repos/vibeacademy/gembaflow/releases/latest" ]]; then
  pass "[fallback] primary URL tried first"
else
  fail "[fallback] expected primary URL first, got: ${URL1:-<none>}"
fi
if [[ "$URL2" == *"/repos/vibeacademy/agile-flow/releases/latest" ]]; then
  pass "[fallback] fallback URL tried after primary 404"
else
  fail "[fallback] expected agile-flow fallback URL second, got: ${URL2:-<none>}"
fi
if grep -q "retrying against fallback vibeacademy/agile-flow" "$WORK_DIR/scen-fallback.log"; then
  pass "[fallback] informational stderr line emitted"
else
  fail "[fallback] expected informational fallback log line"
fi

###############################################################################
# Scenario 4: hybrid agent file merge (#363)
#
# A `.claude/agents/<file>.md` with FRAMEWORK markers + user content outside
# markers must:
#   - get its framework section refreshed from upstream
#   - retain the user content outside the markers byte-for-byte
#
# A legacy file (no markers) must be preserved entirely and the run must warn.
###############################################################################
echo ""
echo "Scenario 4: hybrid .claude/agents/*.md preserves user content outside FRAMEWORK markers"

HYBRID_DIR="$WORK_DIR/hybrid"
mkdir -p "$HYBRID_DIR/scripts/lib" "$HYBRID_DIR/.claude/agents"

cat > "$HYBRID_DIR/.gembaflow-version" <<'JSON'
{
  "version": "0.0.1",
  "syncDirectories": [".claude/agents"]
}
JSON
: > "$HYBRID_DIR/.gembaflow-overrides"

# Local hybrid agent file: framework section (will be replaced) + user content (must survive).
cat > "$HYBRID_DIR/.claude/agents/pr-reviewer.md" <<'MD'
---
name: pr-reviewer
description: Local description (unchanged)
---

<!-- FRAMEWORK:START -->

You are a Staff Engineer (OLD framework text).

<!-- FRAMEWORK:END -->

## Project Context

**Product**: example-site — local user-owned content.
**Bot accounts**: va-worker, va-reviewer.
**Tech stack**: Next.js 15.

This entire block must survive the sync.
MD

# Local legacy agent file: no markers at all.
cat > "$HYBRID_DIR/.claude/agents/system-architect.md" <<'MD'
---
name: system-architect
description: Legacy agent without markers
---

You are a System Architect (legacy text, no FRAMEWORK markers).

## Project Context

This file pre-dates the marker convention; it must NOT be wiped.
MD

cp scripts/template-sync.sh "$HYBRID_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$HYBRID_DIR/scripts/lib/overrides.sh"
chmod +x "$HYBRID_DIR/scripts/template-sync.sh"

# Upstream release: refreshed framework section + a brand-new agent file.
HYBRID_UP="$WORK_DIR/hybrid-upstream/release"
mkdir -p "$HYBRID_UP/.claude/agents"

cat > "$HYBRID_UP/.claude/agents/pr-reviewer.md" <<'MD'
---
name: pr-reviewer
description: Upstream description (will be installed)
---

<!-- FRAMEWORK:START -->

You are a Staff Engineer (NEW framework text v1.0.5).

Additional restrictions:
- New restriction line that did not exist before.

<!-- FRAMEWORK:END -->
MD

cat > "$HYBRID_UP/.claude/agents/system-architect.md" <<'MD'
---
name: system-architect
description: Upstream description
---

<!-- FRAMEWORK:START -->

You are a System Architect (new framework body with markers).

<!-- FRAMEWORK:END -->
MD

tar -czf "$WORK_DIR/hybrid-upstream.tar.gz" -C "$WORK_DIR/hybrid-upstream" release

mkdir -p "$WORK_DIR/hybrid-bin"
cat > "$WORK_DIR/hybrid-bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"/releases/latest"* ]]; then
  printf '{"tag_name":"v1.0.5","html_url":"https://example.invalid/release","tarball_url":"https://example.invalid/hybrid-upstream.tar.gz"}'
  exit 0
fi
if [[ "$*" == *"hybrid-upstream.tar.gz"* ]]; then
  out=''
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then out="$2"; shift 2; continue; fi
    shift
  done
  cp "$TEST_HYBRID_TARBALL" "$out"
  exit 0
fi
exit 1
SH
chmod +x "$WORK_DIR/hybrid-bin/curl"

cat > "$WORK_DIR/hybrid-bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "gh $*" >> "$TEST_HYBRID_GH_LOG"
if [[ "${1:-}" == "auth" && "${2:-}" == "token" ]]; then echo "fake-token"; exit 0; fi
if [[ "${1:-}" == "pr" && "${2:-}" == "create" ]]; then
  # Capture body for later inspection.
  shift
  shift
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--body" ]; then
      echo "$2" > "$TEST_HYBRID_PR_BODY"
      shift 2
      continue
    fi
    shift
  done
  echo "https://example.invalid/pr/363"
  exit 0
fi
if [[ "${1:-}" == "pr" && "${2:-}" == "list" ]]; then echo '[]'; exit 0; fi
exit 0
SH
chmod +x "$WORK_DIR/hybrid-bin/gh"

pushd "$HYBRID_DIR" >/dev/null
git init >/dev/null
git add .
git commit -m "init hybrid" >/dev/null
git init --bare "$WORK_DIR/hybrid-origin.git" >/dev/null
git remote add origin "$WORK_DIR/hybrid-origin.git"
git push -u origin HEAD >/dev/null

TEST_HYBRID_TARBALL="$WORK_DIR/hybrid-upstream.tar.gz" \
TEST_HYBRID_GH_LOG="$WORK_DIR/hybrid-gh.log" \
TEST_HYBRID_PR_BODY="$WORK_DIR/hybrid-pr-body.txt" \
PATH="$WORK_DIR/hybrid-bin:$PATH" \
  bash scripts/template-sync.sh > "$WORK_DIR/hybrid.log" 2>&1 || HYBRID_RC=$?

if grep -q "UPDATED (hybrid framework section): .claude/agents/pr-reviewer.md" "$WORK_DIR/hybrid.log"; then
  pass "[hybrid] pr-reviewer.md framework section reported as updated"
else
  fail "[hybrid] expected UPDATED (hybrid framework section) log line for pr-reviewer.md"
fi

# Marker-aware merge: framework section replaced.
if grep -q "NEW framework text v1.0.5" .claude/agents/pr-reviewer.md; then
  pass "[hybrid] upstream framework body installed in pr-reviewer.md"
else
  fail "[hybrid] expected upstream framework body in pr-reviewer.md"
fi

# User content outside markers preserved.
if grep -q "example-site — local user-owned content" .claude/agents/pr-reviewer.md \
   && grep -q "va-worker, va-reviewer" .claude/agents/pr-reviewer.md \
   && grep -q "This entire block must survive the sync." .claude/agents/pr-reviewer.md; then
  pass "[hybrid] user content outside markers preserved in pr-reviewer.md"
else
  fail "[hybrid] user content outside markers was destroyed in pr-reviewer.md"
fi

# Old framework body must be gone.
if ! grep -q "OLD framework text" .claude/agents/pr-reviewer.md; then
  pass "[hybrid] old framework body removed from pr-reviewer.md"
else
  fail "[hybrid] old framework body still present after sync"
fi

# Frontmatter description must come from upstream, since it's outside the
# markers conceptually — wait: actually frontmatter is OUTSIDE markers, so the
# user's local frontmatter MUST be preserved. Verify.
if grep -q "description: Local description (unchanged)" .claude/agents/pr-reviewer.md; then
  pass "[hybrid] local YAML frontmatter preserved (lives outside markers)"
else
  fail "[hybrid] local YAML frontmatter was overwritten"
fi

# Legacy file: should be preserved entirely and warning emitted.
if grep -q "lacks <!-- FRAMEWORK:START/END --> markers; preserving local file" "$WORK_DIR/hybrid.log"; then
  pass "[hybrid] legacy agent without markers triggers warning"
else
  fail "[hybrid] expected legacy-file warning in log"
fi

if grep -q "legacy text, no FRAMEWORK markers" .claude/agents/system-architect.md \
   && grep -q "This file pre-dates the marker convention" .claude/agents/system-architect.md; then
  pass "[hybrid] legacy agent file content preserved untouched"
else
  fail "[hybrid] legacy agent file was modified"
fi

# Sanity: legacy file should NOT have been forcibly given the upstream body.
if ! grep -q "new framework body with markers" .claude/agents/system-architect.md; then
  pass "[hybrid] legacy agent file was NOT auto-overwritten with upstream body"
else
  fail "[hybrid] legacy agent file was overwritten despite missing markers"
fi

# PR body should mention the hybrid update.
if [ -f "$WORK_DIR/hybrid-pr-body.txt" ] && grep -q "Hybrid agent files updated (framework section only)" "$WORK_DIR/hybrid-pr-body.txt"; then
  pass "[hybrid] PR body announces hybrid updates"
else
  fail "[hybrid] expected PR body to announce hybrid updates"
fi
if [ -f "$WORK_DIR/hybrid-pr-body.txt" ] && grep -q "Legacy agent files (no FRAMEWORK markers)" "$WORK_DIR/hybrid-pr-body.txt"; then
  pass "[hybrid] PR body warns about legacy agent files"
else
  fail "[hybrid] expected PR body to warn about legacy agent files"
fi
popd >/dev/null

###############################################################################
# Scenario 5: package.json version bump (#361)
###############################################################################
# Verifies template-sync.sh writes the new framework version into package.json
# (matching .gembaflow-version), and that re-running on an already-synced repo
# is a no-op (idempotent). Without this, the CI parity check exits non-zero on
# every framework-sync PR.
echo ""
echo "Scenario 5: package.json version is bumped to match release"

PKG_DIR="$WORK_DIR/pkg-bump"
mkdir -p "$PKG_DIR/scripts/lib"
cp scripts/template-sync.sh "$PKG_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$PKG_DIR/scripts/lib/overrides.sh"
chmod +x "$PKG_DIR/scripts/template-sync.sh"
: > "$PKG_DIR/.gembaflow-overrides"

cat > "$PKG_DIR/.gembaflow-version" <<'JSON'
{
  "version": "0.0.1",
  "syncDirectories": ["./scripts"]
}
JSON

cat > "$PKG_DIR/package.json" <<'JSON'
{
  "name": "test-fork",
  "version": "0.0.1",
  "private": true
}
JSON

# Upstream tarball: copies of the runtime-protected script + lib (so the
# protect path keeps the script intact), PLUS a non-protected `scripts/marker.sh`
# whose absence in the fork forces FILES_CHANGED to be non-empty — otherwise
# the sync exits at "Already up to date" before reaching the version-write
# block where the package.json bump lives.
PKG_UPSTREAM="$WORK_DIR/pkg-upstream/vibeacademy-agile-flow-release"
mkdir -p "$PKG_UPSTREAM/scripts/lib"
cp scripts/template-sync.sh "$PKG_UPSTREAM/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$PKG_UPSTREAM/scripts/lib/overrides.sh"
printf '#!/usr/bin/env bash\necho marker\n' > "$PKG_UPSTREAM/scripts/marker.sh"
chmod +x "$PKG_UPSTREAM/scripts/marker.sh"
tar -czf "$WORK_DIR/pkg-upstream.tar.gz" -C "$WORK_DIR/pkg-upstream" vibeacademy-agile-flow-release

mkdir -p "$WORK_DIR/pkg-bin"
cat > "$WORK_DIR/pkg-bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"/releases/latest"* ]]; then
  printf '{"tag_name":"v1.2.0","html_url":"https://example.invalid/release","tarball_url":"https://example.invalid/pkg-upstream.tar.gz"}'
  exit 0
fi
if [[ "$*" == *"pkg-upstream.tar.gz"* ]]; then
  out=''
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  cp "$TEST_PKG_TARBALL" "$out"
  exit 0
fi
exit 1
SH
chmod +x "$WORK_DIR/pkg-bin/curl"

cat > "$WORK_DIR/pkg-bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "auth" && "${2:-}" == "token" ]]; then echo "fake-token"; exit 0; fi
if [[ "${1:-}" == "pr" && "${2:-}" == "create" ]]; then
  echo "https://example.invalid/pr/361"
  exit 0
fi
if [[ "${1:-}" == "pr" && "${2:-}" == "list" ]]; then
  echo '[]'
  exit 0
fi
exit 0
SH
chmod +x "$WORK_DIR/pkg-bin/gh"

pushd "$PKG_DIR" >/dev/null
git init >/dev/null
git -c user.name=test -c user.email=t@t.invalid add .
git -c user.name=test -c user.email=t@t.invalid commit -m "init pkg-bump" >/dev/null
git init --bare "$WORK_DIR/pkg-origin.git" >/dev/null
git remote add origin "$WORK_DIR/pkg-origin.git"
git push -u origin HEAD >/dev/null

if TEST_PKG_TARBALL="$WORK_DIR/pkg-upstream.tar.gz" PATH="$WORK_DIR/pkg-bin:$PATH" bash scripts/template-sync.sh > "$WORK_DIR/pkg-run.log" 2>&1; then
  PKG_VERSION_AFTER=$(python3 -c "import json; print(json.load(open('package.json'))['version'])")
  if [ "$PKG_VERSION_AFTER" = "1.2.0" ]; then
    pass "package.json version bumped to 1.2.0"
  else
    fail "expected package.json version 1.2.0, got: $PKG_VERSION_AFTER"
  fi

  if grep -q "UPDATED: package.json version -> 1.2.0" "$WORK_DIR/pkg-run.log"; then
    pass "package.json bump is logged"
  else
    fail "expected log line 'UPDATED: package.json version -> 1.2.0'"
  fi

  MANIFEST_VERSION_AFTER=$(python3 -c "import json; print(json.load(open('.gembaflow-version'))['version'])")
  if [ "$MANIFEST_VERSION_AFTER" = "$PKG_VERSION_AFTER" ]; then
    pass ".gembaflow-version and package.json agree after sync"
  else
    fail "version mismatch after sync: manifest=$MANIFEST_VERSION_AFTER package=$PKG_VERSION_AFTER"
  fi
else
  cat "$WORK_DIR/pkg-run.log"
  fail "package.json bump scenario failed"
fi
popd >/dev/null

# Idempotent re-run: with .gembaflow-version + package.json already at 1.2.0,
# template-sync should exit cleanly at the "No updates available" check before
# ever touching package.json — proving the bump is safe on re-invocation.
PKG_IDEM_DIR="$WORK_DIR/pkg-idem"
mkdir -p "$PKG_IDEM_DIR/scripts/lib"
cp scripts/template-sync.sh "$PKG_IDEM_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$PKG_IDEM_DIR/scripts/lib/overrides.sh"
chmod +x "$PKG_IDEM_DIR/scripts/template-sync.sh"
: > "$PKG_IDEM_DIR/.gembaflow-overrides"

cat > "$PKG_IDEM_DIR/.gembaflow-version" <<'JSON'
{
  "version": "1.2.0",
  "syncDirectories": ["./scripts"]
}
JSON

cat > "$PKG_IDEM_DIR/package.json" <<'JSON'
{
  "name": "test-fork",
  "version": "1.2.0",
  "private": true
}
JSON

pushd "$PKG_IDEM_DIR" >/dev/null
git init >/dev/null
git -c user.name=test -c user.email=t@t.invalid add .
git -c user.name=test -c user.email=t@t.invalid commit -m "init pkg-idem" >/dev/null

PKG_IDEM_BEFORE=$(sha256sum package.json | awk '{print $1}')
if TEST_PKG_TARBALL="$WORK_DIR/pkg-upstream.tar.gz" PATH="$WORK_DIR/pkg-bin:$PATH" bash scripts/template-sync.sh > "$WORK_DIR/pkg-idem.log" 2>&1; then
  PKG_IDEM_AFTER=$(sha256sum package.json | awk '{print $1}')
  if [ "$PKG_IDEM_BEFORE" = "$PKG_IDEM_AFTER" ]; then
    pass "idempotent: package.json unchanged when versions already match"
  else
    fail "package.json mutated on idempotent re-run"
  fi

  if grep -q "No updates available" "$WORK_DIR/pkg-idem.log"; then
    pass "idempotent re-run exits cleanly at version-equal check"
  else
    fail "expected 'No updates available' on idempotent run"
  fi
else
  cat "$WORK_DIR/pkg-idem.log"
  fail "idempotent re-run failed"
fi
popd >/dev/null

echo "Results: ${TESTS_PASSED} passed, ${TESTS_FAILED} failed"
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
