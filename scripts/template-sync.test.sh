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

echo "Results: ${TESTS_PASSED} passed, ${TESTS_FAILED} failed"
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
