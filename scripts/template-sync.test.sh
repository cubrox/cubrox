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

cat > "$REPO_DIR/.agile-flow-version" <<'JSON'
{
  "version": "0.1.0",
  "syncDirectories": [
    "./scripts"
  ]
}
JSON

: > "$REPO_DIR/.agile-flow-overrides"

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

cat > "$REENTRY_DIR/.agile-flow-version" <<'JSON'
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
git add scripts/template-sync.sh .agile-flow-version

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

  if git show-ref --verify --quiet refs/heads/agile-flow-sync/v1.0.4; then
    pass "re-entry path creates local sync branch"
  else
    fail "expected local sync branch agile-flow-sync/v1.0.4"
  fi

  if git --git-dir "$WORK_DIR/reentry-origin.git" show-ref --verify --quiet refs/heads/agile-flow-sync/v1.0.4; then
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
  : > "$scenario_dir/.agile-flow-overrides"

  if [ -n "$upstream_field" ]; then
    cat > "$scenario_dir/.agile-flow-version" <<JSON
{
  "version": "9.9.9",
  "upstream": "$upstream_field",
  "syncDirectories": ["./scripts"]
}
JSON
  else
    cat > "$scenario_dir/.agile-flow-version" <<'JSON'
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
run_upstream_scenario "upstream-honored" "vibeacademy/agile-flow-gcp" "vibeacademy/agile-flow-gcp" ""

# (a2) upstream URL form normalized to owner/repo
run_upstream_scenario "upstream-url-normalized" "https://github.com/vibeacademy/agile-flow-gcp" "vibeacademy/agile-flow-gcp" ""

# (b) absent upstream falls back to hardcoded default
run_upstream_scenario "upstream-absent" "" "vibeacademy/agile-flow" ""

# (c) 404 from primary -> fallback URL is tried
FAIL_URL="https://api.github.com/repos/vibeacademy/agile-flow/releases/latest"
SCEN_DIR="$WORK_DIR/scen-fallback"
mkdir -p "$SCEN_DIR/scripts/lib"
cp scripts/template-sync.sh "$SCEN_DIR/scripts/template-sync.sh"
cp scripts/lib/overrides.sh "$SCEN_DIR/scripts/lib/overrides.sh"
chmod +x "$SCEN_DIR/scripts/template-sync.sh"
: > "$SCEN_DIR/.agile-flow-overrides"
cat > "$SCEN_DIR/.agile-flow-version" <<'JSON'
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
if [[ "$URL1" == *"/repos/vibeacademy/agile-flow/releases/latest" ]]; then
  pass "[fallback] primary URL tried first"
else
  fail "[fallback] expected primary URL first, got: ${URL1:-<none>}"
fi
if [[ "$URL2" == *"/repos/vibeacademy/gembaflow/releases/latest" ]]; then
  pass "[fallback] fallback URL tried after primary 404"
else
  fail "[fallback] expected gembaflow fallback URL second, got: ${URL2:-<none>}"
fi
if grep -q "retrying against fallback vibeacademy/gembaflow" "$WORK_DIR/scen-fallback.log"; then
  pass "[fallback] informational stderr line emitted"
else
  fail "[fallback] expected informational fallback log line"
fi

echo "Results: ${TESTS_PASSED} passed, ${TESTS_FAILED} failed"
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
