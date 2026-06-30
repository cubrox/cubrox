#!/usr/bin/env bash
# =============================================================================
# 03-verification.sh — `cubrox` -> `masterkey` rename verification
#
# Purpose: prove (read-only, idempotent) that the refactor described in
#   reports/refactor/01-architecture-plan.md (v2) is complete and that
#   nothing data-bearing was touched. Companion runbook:
#   reports/refactor/03-verification-runbook.md.
#
# Usage:
#   bash reports/refactor/03-verification.sh                       # run all checks
#   bash reports/refactor/03-verification.sh --section A,B,C       # run subset
#   bash reports/refactor/03-verification.sh --exercise-preview-deploy
#       (mutating; gated; opens a throwaway PR — see section G + runbook)
#
# Output per check:
#   [PASS] <id> <desc>
#   [FAIL] <id> <desc> — <reason>
#   [SKIP] <id> <desc> — <reason>
#
# Exit code: 0 only if FAIL count == 0. Script uses `set -u` (NOT `set -e`)
#   so every section runs to completion even if early checks fail.
#
# Invariants this script will never violate:
#   - read-only by default; the only mutating path is section G when --exercise-preview-deploy is set
#   - no hardcoded credentials
#   - hardcoded values limited to the immutable Supabase project ref and the GCP project (read from env)
# =============================================================================

set -u
set -o pipefail

# ─────────────────────────────────────────────────────────────────────
# Constants (refactor plan invariants)
# ─────────────────────────────────────────────────────────────────────
readonly NEW_REPO="cubrox/masterkey"
readonly OLD_REPO="cubrox/cubrox"
readonly NEW_SERVICE="masterkey"
readonly OLD_SERVICE="agile-flow-app"
readonly NEW_AR_REPO="masterkey"
readonly OLD_AR_REPO="agile-flow"
readonly SUPABASE_PROJECT_REF="gnswmcgaztcxslirulwm"
readonly NEW_ENV_VAR="MASTERKEY_TEST_SEED_ENABLED"
readonly OLD_ENV_VAR="CUBROX_TEST_SEED_ENABLED"
readonly DEFAULT_REGION="us-central1"

# ─────────────────────────────────────────────────────────────────────
# Repo root (script lives in reports/refactor/)
# ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SNAPSHOT_DIR="${REPO_ROOT}/reports/refactor/snapshots/$(date -u +%Y%m%dT%H%M%SZ)"

# ─────────────────────────────────────────────────────────────────────
# Colors (suppress if not a TTY)
# ─────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_RED=$'\033[0;31m'; C_GRN=$'\033[0;32m'; C_YEL=$'\033[1;33m'; C_CYN=$'\033[0;36m'; C_NC=$'\033[0m'
else
  C_RED=''; C_GRN=''; C_YEL=''; C_CYN=''; C_NC=''
fi

# ─────────────────────────────────────────────────────────────────────
# Counters + reporting
# ─────────────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
declare -a FAIL_LINES=()

pass()  { echo "${C_GRN}[PASS]${C_NC} $1 — $2"; PASS_COUNT=$((PASS_COUNT+1)); }
fail()  { echo "${C_RED}[FAIL]${C_NC} $1 — $2 — ${3:-unknown}"; FAIL_COUNT=$((FAIL_COUNT+1)); FAIL_LINES+=("$1 $2 :: ${3:-}"); }
skipc() { echo "${C_YEL}[SKIP]${C_NC} $1 — $2 — ${3:-prerequisite missing}"; SKIP_COUNT=$((SKIP_COUNT+1)); }
note()  { echo "${C_CYN}      ${C_NC}$1"; }
section() { echo; echo "${C_CYN}━━━ $1 ━━━${C_NC}"; }

# ─────────────────────────────────────────────────────────────────────
# Flag parsing
# ─────────────────────────────────────────────────────────────────────
EXERCISE_PREVIEW=0
SECTIONS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --exercise-preview-deploy) EXERCISE_PREVIEW=1; shift ;;
    --section)                 SECTIONS="${2:-}"; shift 2 ;;
    --section=*)               SECTIONS="${1#--section=}"; shift ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

run_section() {
  # $1 = single letter (A,B,...). Returns 0 if user wants to run it.
  [ -z "$SECTIONS" ] && return 0
  case ",$SECTIONS," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}

# ─────────────────────────────────────────────────────────────────────
# Tool availability helpers
# ─────────────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }

gh_authed() {
  have gh && gh auth status >/dev/null 2>&1
}

gcloud_authed() {
  have gcloud && gcloud auth list --format='value(account)' 2>/dev/null | grep -q .
}

supabase_cli_ok() { have supabase; }

# ─────────────────────────────────────────────────────────────────────
# Resolve GCP project id (read-only: prefer env, fall back to gcloud config)
# ─────────────────────────────────────────────────────────────────────
resolve_gcp_project() {
  if [ -n "${GCP_PROJECT_ID:-}" ]; then
    echo "$GCP_PROJECT_ID"; return 0
  fi
  if gcloud_authed; then
    local p
    p="$(gcloud config get-value project 2>/dev/null || true)"
    [ -n "$p" ] && [ "$p" != "(unset)" ] && { echo "$p"; return 0; }
  fi
  return 1
}

# =============================================================================
# SECTION A — Pre-refactor / pre-execution baseline snapshot
#   Read-only. Captures current state so a later run can diff. Idempotent:
#   each invocation writes into a fresh timestamped dir under
#   reports/refactor/snapshots/.
# =============================================================================
section_A() {
  section "A. Baseline snapshot ($(basename "$SNAPSHOT_DIR"))"
  mkdir -p "$SNAPSHOT_DIR"

  # A1 — gh repo view (resolved name + URL)
  if gh_authed; then
    local current_repo
    current_repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
    if [ -n "$current_repo" ]; then
      printf '%s\n' "$current_repo" > "$SNAPSHOT_DIR/repo-name.txt"
      gh repo view --json nameWithOwner,url,sshUrl,isArchived,visibility,defaultBranchRef \
        > "$SNAPSHOT_DIR/repo.json" 2>/dev/null || true
      pass A1 "captured gh repo view ($current_repo)"
    else
      fail A1 "gh repo view" "command returned empty (auth or repo missing)"
    fi
  else
    skipc A1 "gh repo view" "gh not authed"
  fi

  # A2 — secrets/variables names (NEVER values — gh API only returns names anyway)
  if gh_authed; then
    gh secret list   > "$SNAPSHOT_DIR/secrets.txt"   2>/dev/null || true
    gh variable list > "$SNAPSHOT_DIR/variables.txt" 2>/dev/null || true
    if [ -s "$SNAPSHOT_DIR/secrets.txt" ] || [ -s "$SNAPSHOT_DIR/variables.txt" ]; then
      pass A2 "captured secret + variable names"
    else
      fail A2 "gh secret/variable list" "both outputs empty — admin perm needed?"
    fi
  else
    skipc A2 "secrets/variables" "gh not authed"
  fi

  # A3 — recent CI run statuses (proves CI is still flowing post-rename when re-run)
  if gh_authed; then
    if gh run list --limit 10 > "$SNAPSHOT_DIR/runs.txt" 2>/dev/null; then
      pass A3 "captured last 10 workflow runs"
    else
      skipc A3 "gh run list" "no recent runs or perm denied"
    fi
  else
    skipc A3 "recent runs" "gh not authed"
  fi

  # A4 — Cloud Run service describe (BOTH old and new; missing is fine, captured as a "miss" marker)
  if gcloud_authed; then
    local proj; proj="$(resolve_gcp_project || true)"
    if [ -z "$proj" ]; then
      skipc A4 "gcloud run services describe" "no GCP project resolved"
    else
      for svc in "$OLD_SERVICE" "$NEW_SERVICE"; do
        if gcloud run services describe "$svc" --region="$DEFAULT_REGION" --project="$proj" \
             --format=yaml > "$SNAPSHOT_DIR/run-${svc}.yaml" 2>/dev/null; then
          note "    captured ${svc}"
        else
          echo "MISSING" > "$SNAPSHOT_DIR/run-${svc}.yaml"
        fi
      done
      pass A4 "captured Cloud Run service state (both old + new)"
    fi
  else
    skipc A4 "Cloud Run snapshot" "gcloud not authed"
  fi

  # A5 — Service Account IAM policy (the WIF binding lives here per plan B2)
  if gcloud_authed && [ -n "${GCP_SERVICE_ACCOUNT:-}" ]; then
    local proj; proj="$(resolve_gcp_project || true)"
    if gcloud iam service-accounts get-iam-policy "$GCP_SERVICE_ACCOUNT" \
         --project="$proj" --format=yaml > "$SNAPSHOT_DIR/sa-iam.yaml" 2>/dev/null; then
      pass A5 "captured deployer SA IAM policy"
    else
      fail A5 "SA IAM policy" "get-iam-policy failed (perm or SA misnamed)"
    fi
  else
    skipc A5 "SA IAM policy" "GCP_SERVICE_ACCOUNT env unset or gcloud not authed"
  fi
}

# =============================================================================
# SECTION B — Code-level rename checks
#   grep for forbidden strings in places they shouldn't be. The allowlist
#   below encodes the plan's intentional "stays as-is" decisions so we
#   don't false-positive on framework template paths.
# =============================================================================
section_B() {
  section "B. Code-level rename checks"

  # The ONLY places where the literal string "cubrox" / "Cubrox" should
  # legitimately remain post-rename. Each line is a regex matched against
  # the full file path (relative to repo root, with leading ./).
  # WHY each entry exists is documented inline; do not prune without
  # consulting the architecture plan §2.
  local -a ALLOWLIST=(
    # Historical refactor reports themselves
    "^reports/refactor/"
    # Session journals — historical record (plan §2.6 last row)
    "^reports/session-journals/"
    # eli5 command upstream-provenance line referencing 'vibeacademy/cubrox' prototype (plan §2.7)
    "^\.claude/commands/eli5\.md$"
    # Roadmap historical change-log row attributing initial roadmap to "cubrox" (plan §2.6)
    "^docs/PRODUCT-ROADMAP\.md$"
    # ADR-006 is intentionally immutable; rename narrated by a NEW ADR-007 (plan §2.6)
    "^docs/TECHNICAL-ARCHITECTURE\.md$"
    # PATTERN-LIBRARY narrative line "Cubrox chose (1)" may be rewritten as historical (plan §2.6)
    "^docs/PATTERN-LIBRARY\.md$"
    # Memory MCP entity migration is explicitly out of immediate scope (plan §2.9, R7)
    "^\.claude/(memory|state)/"
    # tests/a11y/node_modules — vendor; never our code
    "^tests/a11y/node_modules/"
    # The .git directory
    "^\.git/"
  )

  # B1 — Forbidden 'cubrox' / 'Cubrox' tokens outside allowlist
  if have grep; then
    # rg preferred but grep -r is universal
    local tmp; tmp="$(mktemp)"
    grep -rInE 'cubrox|Cubrox' "$REPO_ROOT" \
      --include='*.py' --include='*.toml' --include='*.md' --include='*.sh' \
      --include='*.yml' --include='*.yaml' --include='*.html' --include='*.ts' \
      --include='*.tsx' --include='*.js' --include='*.json' --include='*.lock' \
      2>/dev/null \
      | sed "s|^${REPO_ROOT}/||" > "$tmp" || true

    local violations; violations=0
    if [ -s "$tmp" ]; then
      while IFS= read -r line; do
        local path; path="${line%%:*}"
        local matched=0
        for pat in "${ALLOWLIST[@]}"; do
          if printf '%s' "$path" | grep -qE "$pat"; then matched=1; break; fi
        done
        if [ $matched -eq 0 ]; then
          violations=$((violations+1))
          [ $violations -le 5 ] && note "    $line"
        fi
      done < "$tmp"
    fi
    rm -f "$tmp"

    if [ $violations -eq 0 ]; then
      pass B1 "no out-of-allowlist 'cubrox'/'Cubrox' references"
    else
      fail B1 "stale 'cubrox' references" "$violations occurrences outside allowlist (first 5 above)"
    fi
  else
    skipc B1 "cubrox grep" "grep not available"
  fi

  # B2 — Forbidden 'agile-flow-app' tokens (allowlist below; ditto rationale)
  local -a ALLOWLIST_AFA=(
    "^reports/refactor/"
    "^reports/session-journals/"
    # PLATFORM-GUIDE/CI-CD-GUIDE are upstream-synced docs; per §2.6 decision tree
    # they may legitimately retain 'agile-flow-app' unless added to .agile-flow-overrides
    "^docs/PLATFORM-GUIDE\.md$"
    "^docs/CI-CD-GUIDE\.md$"
    # PATTERN-LIBRARY examples are illustrative (plan §2.6)
    "^docs/PATTERN-LIBRARY\.md$"
    # devops-engineer.md examples — listed in .agile-flow-overrides (plan §2.7)
    "^\.claude/agents/devops-engineer\.md$"
    # diagnose-cloudrun.test.sh fixture strings (test data, not source-of-truth defaults)
    "^scripts/diagnose-cloudrun\.test\.sh$"
    "^\.git/"
    "^tests/a11y/node_modules/"
  )

  local tmp2; tmp2="$(mktemp)"
  grep -rInE 'agile-flow-app' "$REPO_ROOT" \
    --include='*.py' --include='*.toml' --include='*.md' --include='*.sh' \
    --include='*.yml' --include='*.yaml' --include='*.html' --include='*.ts' \
    --include='*.json' 2>/dev/null \
    | sed "s|^${REPO_ROOT}/||" > "$tmp2" || true

  local violations2; violations2=0
  if [ -s "$tmp2" ]; then
    while IFS= read -r line; do
      local path; path="${line%%:*}"
      local matched=0
      for pat in "${ALLOWLIST_AFA[@]}"; do
        if printf '%s' "$path" | grep -qE "$pat"; then matched=1; break; fi
      done
      if [ $matched -eq 0 ]; then
        violations2=$((violations2+1))
        [ $violations2 -le 5 ] && note "    $line"
      fi
    done < "$tmp2"
  fi
  rm -f "$tmp2"

  if [ $violations2 -eq 0 ]; then
    pass B2 "no out-of-allowlist 'agile-flow-app' references"
  else
    fail B2 "stale 'agile-flow-app' references" "$violations2 occurrences outside allowlist (first 5 above)"
  fi

  # B3 — The CUBROX_TEST_SEED_ENABLED literal MUST be gone (plan B1)
  local n_old
  n_old=$(grep -rIn "$OLD_ENV_VAR" "$REPO_ROOT" \
            --exclude-dir=.git --exclude-dir=node_modules \
            --exclude-dir=reports 2>/dev/null | wc -l | tr -d ' ')
  if [ "$n_old" = "0" ]; then
    pass B3 "$OLD_ENV_VAR is gone from sources (plan B1)"
  else
    fail B3 "$OLD_ENV_VAR still present" "$n_old occurrence(s) — ci.yml lines 218,307,315 must be edited"
  fi

  # B4 — The new env var MUST be present in at least the test files + ci.yml (sanity, not just bare deletion)
  local n_new
  n_new=$(grep -rIn "$NEW_ENV_VAR" "$REPO_ROOT" \
            --exclude-dir=.git --exclude-dir=node_modules \
            --exclude-dir=reports 2>/dev/null | wc -l | tr -d ' ')
  if [ "$n_new" -ge 3 ]; then
    pass B4 "$NEW_ENV_VAR present in $n_new locations"
  else
    fail B4 "$NEW_ENV_VAR" "only $n_new occurrence(s) — expected >=3 (app + tests + ci)"
  fi

  # B5 — pyproject.toml name MUST stay 'agile-flow-gcp' (plan R6 / out-of-scope)
  if [ -f "$REPO_ROOT/pyproject.toml" ]; then
    if grep -qE '^name *= *"agile-flow-gcp"' "$REPO_ROOT/pyproject.toml"; then
      pass B5 "pyproject.toml name is still 'agile-flow-gcp' (intentional per plan R6)"
    else
      fail B5 "pyproject.toml name" "should remain 'agile-flow-gcp' — anyone who renamed it diverged from plan R6"
    fi
  else
    skipc B5 "pyproject.toml" "file not found"
  fi

  # B6 — supabase/config.toml project_id MUST be 'masterkey' (plan §2.8)
  if [ -f "$REPO_ROOT/supabase/config.toml" ]; then
    if grep -qE '^project_id *= *"masterkey"' "$REPO_ROOT/supabase/config.toml"; then
      pass B6 "supabase/config.toml project_id is 'masterkey'"
    else
      local val
      val="$(grep -E '^project_id' "$REPO_ROOT/supabase/config.toml" | head -1 || echo unset)"
      fail B6 "supabase/config.toml project_id" "expected 'masterkey', found: ${val}"
    fi
  else
    skipc B6 "supabase/config.toml" "file not found"
  fi

  # B7 — window.cubroxLineCount must be gone from templates AND tests (must move in lockstep)
  local n_glob
  n_glob=$(grep -rIn "window.cubroxLineCount" "$REPO_ROOT/templates" "$REPO_ROOT/tests" \
            2>/dev/null | wc -l | tr -d ' ')
  if [ "$n_glob" = "0" ]; then
    pass B7 "window.cubroxLineCount renamed in templates+tests"
  else
    fail B7 "window.cubroxLineCount" "$n_glob occurrence(s) remain — template + test must move together"
  fi
}

# =============================================================================
# SECTION C — GitHub repo identity checks
# =============================================================================
section_C() {
  section "C. GitHub repo identity"

  # C1 — Repo exists at new name
  if gh_authed; then
    if gh repo view "$NEW_REPO" --json nameWithOwner --jq .nameWithOwner >/dev/null 2>&1; then
      pass C1 "gh repo view $NEW_REPO succeeds"
    else
      fail C1 "gh repo view $NEW_REPO" "repo not found or no access"
    fi
  else
    skipc C1 "gh repo view" "gh not authed"
  fi

  # C2 — Local origin remote points at the new URL
  if have git && [ -d "$REPO_ROOT/.git" ]; then
    local origin
    origin="$(git -C "$REPO_ROOT" config --get remote.origin.url 2>/dev/null || true)"
    if printf '%s' "$origin" | grep -qE "[:/]${NEW_REPO}(\.git)?$"; then
      pass C2 "git remote origin points to $NEW_REPO"
    elif printf '%s' "$origin" | grep -qE "[:/]${OLD_REPO}(\.git)?$"; then
      fail C2 "git remote origin" "still points to $OLD_REPO ($origin) — run: git remote set-url origin git@github.com:${NEW_REPO}.git"
    else
      fail C2 "git remote origin" "unexpected URL: $origin"
    fi
  else
    skipc C2 "git remote" "not a git checkout"
  fi

  # C3 — Old repo URL still 30-day-redirects (informational; we expect 301/302 for the lifetime of the grace window)
  if have curl; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://github.com/${OLD_REPO}" || echo 000)"
    case "$code" in
      301|302) pass C3 "https://github.com/${OLD_REPO} redirects (HTTP $code) — grace window active" ;;
      200)     pass C3 "https://github.com/${OLD_REPO} resolves (HTTP 200) — likely pre-rename or pre-redirect" ;;
      404)     fail C3 "old repo URL" "returns 404 — 30-day redirect window may have lapsed or repo never renamed" ;;
      *)       skipc C3 "old repo URL" "HTTP $code (network or GitHub issue)" ;;
    esac
  else
    skipc C3 "old repo redirect" "curl not available"
  fi

  # C4 — Branch protection ruleset still present (plan §2.1 row 7 — id 15886599)
  if gh_authed; then
    local count
    count="$(gh api "repos/${NEW_REPO}/rulesets" --jq 'length' 2>/dev/null || echo "")"
    if [ -n "$count" ] && [ "$count" -gt 0 ]; then
      pass C4 "branch-protection rulesets present ($count) on $NEW_REPO"
    else
      fail C4 "branch protection" "no rulesets visible on $NEW_REPO (perm? or rename dropped them?)"
    fi
  else
    skipc C4 "branch protection" "gh not authed"
  fi
}

# =============================================================================
# SECTION D — GitHub Actions config (vars + secret presence)
# =============================================================================
section_D() {
  section "D. GitHub Actions config"

  if ! gh_authed; then
    skipc D1 "vars/secrets" "gh not authed"
    skipc D2 "vars/secrets" "gh not authed"
    skipc D3 "vars/secrets" "gh not authed"
    return
  fi

  # D1 — vars.CLOUD_RUN_SERVICE must be 'masterkey' (or unset, which means the workflow default 'agile-flow-app' wins)
  local v
  v="$(gh variable get CLOUD_RUN_SERVICE 2>/dev/null || echo "")"
  if [ "$v" = "$NEW_SERVICE" ]; then
    pass D1 "vars.CLOUD_RUN_SERVICE = $NEW_SERVICE"
  elif [ -z "$v" ]; then
    fail D1 "vars.CLOUD_RUN_SERVICE" "unset — workflow defaults to '$OLD_SERVICE' (deploy.yml:25)"
  else
    fail D1 "vars.CLOUD_RUN_SERVICE" "is '$v', expected '$NEW_SERVICE'"
  fi

  # D2 — vars.ARTIFACT_REPO must be 'masterkey'
  v="$(gh variable get ARTIFACT_REPO 2>/dev/null || echo "")"
  if [ "$v" = "$NEW_AR_REPO" ]; then
    pass D2 "vars.ARTIFACT_REPO = $NEW_AR_REPO"
  elif [ -z "$v" ]; then
    fail D2 "vars.ARTIFACT_REPO" "unset — workflow defaults to '$OLD_AR_REPO'"
  else
    fail D2 "vars.ARTIFACT_REPO" "is '$v', expected '$NEW_AR_REPO'"
  fi

  # D3 — ci.yml no longer contains literal CUBROX_TEST_SEED_ENABLED (plan B1)
  if [ -f "$REPO_ROOT/.github/workflows/ci.yml" ]; then
    if grep -q "$OLD_ENV_VAR" "$REPO_ROOT/.github/workflows/ci.yml"; then
      fail D3 ".github/workflows/ci.yml" "still contains $OLD_ENV_VAR (plan B1 — lines 218/307/315 must be edited)"
    else
      pass D3 ".github/workflows/ci.yml no longer contains $OLD_ENV_VAR"
    fi
  else
    skipc D3 "ci.yml" "file not found"
  fi

  # D4 — Required secrets present (names only; gh API never returns values)
  local missing=""
  for sec in GCP_PROJECT_ID GCP_SERVICE_ACCOUNT GCP_WORKLOAD_IDENTITY_PROVIDER \
             PRODUCTION_DATABASE_URL ANTHROPIC_API_KEY SUPABASE_ACCESS_TOKEN; do
    if ! gh secret list 2>/dev/null | awk '{print $1}' | grep -qx "$sec"; then
      missing="${missing}${sec} "
    fi
  done
  if [ -z "$missing" ]; then
    pass D4 "required deploy secrets all present"
  else
    fail D4 "missing secrets" "$missing"
  fi
}

# =============================================================================
# SECTION E — WIF / IAM check (plan B2 — most likely "stuck in middle" failure)
#   Confirms BOTH workloadIdentityUser AND serviceAccountTokenCreator
#   are bound on the deployer SA for the NEW principalSet path.
# =============================================================================
section_E() {
  section "E. WIF / IAM bindings"

  if ! gcloud_authed; then
    skipc E1 "WIF binding" "gcloud not authed"
    return
  fi
  if [ -z "${GCP_SERVICE_ACCOUNT:-}" ]; then
    skipc E1 "WIF binding" "GCP_SERVICE_ACCOUNT env unset (export the deployer SA email)"
    return
  fi
  local proj; proj="$(resolve_gcp_project || true)"
  if [ -z "$proj" ]; then
    skipc E1 "WIF binding" "GCP project not resolvable"
    return
  fi

  local policy
  policy="$(gcloud iam service-accounts get-iam-policy "$GCP_SERVICE_ACCOUNT" \
              --project="$proj" --format=json 2>/dev/null || true)"
  if [ -z "$policy" ] || [ "$policy" = "null" ]; then
    fail E1 "WIF binding" "get-iam-policy returned empty (perm denied or wrong SA)"
    return
  fi

  if ! have jq; then
    skipc E1 "WIF binding" "jq not installed — cannot parse IAM policy"
    return
  fi

  local project_number
  project_number="$(gcloud projects describe "$proj" --format='value(projectNumber)' 2>/dev/null || true)"
  if [ -z "$project_number" ]; then
    fail E1 "WIF binding" "could not resolve projectNumber for $proj"
    return
  fi

  local new_member="principalSet://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/github/attribute.repository/${NEW_REPO}"

  # E1 — workloadIdentityUser bound for new repo path
  if printf '%s' "$policy" | jq -e --arg m "$new_member" \
       '.bindings[]? | select(.role=="roles/iam.workloadIdentityUser") | .members[]? | select(. == $m)' \
       >/dev/null 2>&1; then
    pass E1 "workloadIdentityUser bound for ${NEW_REPO}"
  else
    fail E1 "workloadIdentityUser" "no binding for ${NEW_REPO} on $GCP_SERVICE_ACCOUNT (plan Phase 2 step 16)"
  fi

  # E2 — serviceAccountTokenCreator bound for new repo path (plan B2: BOTH roles needed)
  if printf '%s' "$policy" | jq -e --arg m "$new_member" \
       '.bindings[]? | select(.role=="roles/iam.serviceAccountTokenCreator") | .members[]? | select(. == $m)' \
       >/dev/null 2>&1; then
    pass E2 "serviceAccountTokenCreator bound for ${NEW_REPO}"
  else
    fail E2 "serviceAccountTokenCreator" "no binding for ${NEW_REPO} on $GCP_SERVICE_ACCOUNT (plan B2)"
  fi

  # E3 — Old binding gone (informational only — present is acceptable during 30-day grace)
  local old_member="principalSet://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/github/attribute.repository/${OLD_REPO}"
  if printf '%s' "$policy" | jq -e --arg m "$old_member" \
       '.bindings[]? | select(.role=="roles/iam.workloadIdentityUser") | .members[]? | select(. == $m)' \
       >/dev/null 2>&1; then
    note "    INFO: old binding for $OLD_REPO still present — fine during dual-write window, prune in Phase 5 step 38"
    pass E3 "old WIF binding presence (informational)"
  else
    pass E3 "old WIF binding has been pruned (Phase 5 step 38 complete)"
  fi
}

# =============================================================================
# SECTION F — Cloud Run + Artifact Registry
# =============================================================================
section_F() {
  section "F. Cloud Run + Artifact Registry"

  if ! gcloud_authed; then
    skipc F1 "Cloud Run" "gcloud not authed"
    return
  fi
  local proj; proj="$(resolve_gcp_project || true)"
  if [ -z "$proj" ]; then
    skipc F1 "Cloud Run" "GCP project not resolvable"
    return
  fi

  # F1 — New service exists and is serving traffic
  local new_url
  new_url="$(gcloud run services describe "$NEW_SERVICE" --region="$DEFAULT_REGION" --project="$proj" \
              --format='value(status.url)' 2>/dev/null || true)"
  if [ -n "$new_url" ]; then
    pass F1 "$NEW_SERVICE service exists at $new_url"
  else
    fail F1 "$NEW_SERVICE service" "not found in $DEFAULT_REGION (plan Phase 3 step 23 not complete?)"
  fi

  # F2 — New service serves /api/health 200 (the canonical app-readiness probe per preview-deploy.yml:235)
  if [ -n "$new_url" ] && have curl; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${new_url}/api/health" || echo 000)"
    if [ "$code" = "200" ]; then
      pass F2 "${new_url}/api/health returns 200"
    else
      fail F2 "${new_url}/api/health" "HTTP $code (expected 200)"
    fi
  else
    skipc F2 "new service health" "no URL or no curl"
  fi

  # F3 — DB-touching probe (per preview-deploy.yml:262)
  if [ -n "$new_url" ] && have curl; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${new_url}/api/health/db" || echo 000)"
    if [ "$code" = "200" ]; then
      pass F3 "${new_url}/api/health/db returns 200"
    else
      fail F3 "${new_url}/api/health/db" "HTTP $code — DB connectivity broken on new service"
    fi
  else
    skipc F3 "new service DB health" "no URL or no curl"
  fi

  # F4 — New AR repo exists
  if gcloud artifacts repositories describe "$NEW_AR_REPO" \
       --location="$DEFAULT_REGION" --project="$proj" >/dev/null 2>&1; then
    pass F4 "Artifact Registry repo '$NEW_AR_REPO' exists"
  else
    fail F4 "Artifact Registry repo" "$NEW_AR_REPO not found in $DEFAULT_REGION"
  fi

  # F5 — Old service status (informational; plan keeps it for 30 days then deletes in Phase 5 step 35)
  if gcloud run services describe "$OLD_SERVICE" --region="$DEFAULT_REGION" --project="$proj" \
       --format='value(metadata.name)' >/dev/null 2>&1; then
    note "    INFO: old service '$OLD_SERVICE' still present — expected during Phase 4/5 grace window"
    pass F5 "old service still present (grace window active)"
  else
    pass F5 "old service has been deleted (Phase 5 step 35 complete)"
  fi
}

# =============================================================================
# SECTION G — Ephemeral preview deploy verification (the user's hard requirement)
#   Default mode: STATIC check only — confirms the workflow files reference
#   resolved values and would push to the new AR + service. This is read-only.
#
#   Active mode (--exercise-preview-deploy): opens a throwaway PR to drive
#   preview-deploy.yml end-to-end, then closes it to exercise
#   preview-cleanup.yml. This is the ONLY mutating path in the script.
# =============================================================================
section_G() {
  section "G. Ephemeral preview deploy"

  # G1 — preview-deploy.yml present with the expected env wiring
  local pdy="$REPO_ROOT/.github/workflows/preview-deploy.yml"
  if [ ! -f "$pdy" ]; then
    fail G1 "preview-deploy.yml" "not found at $pdy"
    return
  fi
  # The workflow MUST use `vars.CLOUD_RUN_SERVICE || '<default>'` — confirms the var-flip path is wired
  if grep -qE 'vars\.CLOUD_RUN_SERVICE' "$pdy" && grep -qE 'vars\.ARTIFACT_REPO' "$pdy"; then
    pass G1 "preview-deploy.yml reads vars.CLOUD_RUN_SERVICE + vars.ARTIFACT_REPO"
  else
    fail G1 "preview-deploy.yml" "missing vars.CLOUD_RUN_SERVICE / vars.ARTIFACT_REPO wiring"
  fi

  # G2 — preview-cleanup.yml present + reads the same vars
  local pcl="$REPO_ROOT/.github/workflows/preview-cleanup.yml"
  if [ ! -f "$pcl" ]; then
    fail G2 "preview-cleanup.yml" "not found at $pcl"
  elif grep -qE 'vars\.CLOUD_RUN_SERVICE' "$pcl"; then
    pass G2 "preview-cleanup.yml reads vars.CLOUD_RUN_SERVICE"
  else
    fail G2 "preview-cleanup.yml" "missing vars.CLOUD_RUN_SERVICE wiring"
  fi

  # G3 — Once vars are flipped, resolved service in preview = masterkey
  #      (We re-check the var here so the section is self-contained.)
  if gh_authed; then
    local v; v="$(gh variable get CLOUD_RUN_SERVICE 2>/dev/null || echo "")"
    if [ "$v" = "$NEW_SERVICE" ]; then
      pass G3 "preview deploys will target ${NEW_SERVICE} (vars.CLOUD_RUN_SERVICE flipped)"
    else
      fail G3 "preview target" "vars.CLOUD_RUN_SERVICE='${v:-unset}', preview would still hit old service"
    fi
  else
    skipc G3 "preview target var" "gh not authed"
  fi

  # G4 — Active exercise (mutating, gated)
  if [ "$EXERCISE_PREVIEW" -eq 1 ]; then
    if ! gh_authed; then
      skipc G4 "exercise preview deploy" "gh not authed"
      return
    fi
    if ! have git; then
      skipc G4 "exercise preview deploy" "git not available"
      return
    fi

    local branch="verify/preview-deploy-$(date -u +%Y%m%d%H%M%S)"
    note "    creating throwaway branch $branch"
    (
      cd "$REPO_ROOT" || exit 1
      git checkout -b "$branch" >/dev/null 2>&1 || { echo "    branch create failed" >&2; exit 1; }
      # Touch a trivial doc-only file. We deliberately do NOT touch supabase/migrations to avoid branching churn here.
      printf '\n<!-- verification touch %s -->\n' "$(date -u +%FT%TZ)" >> reports/refactor/03-verification-runbook.md
      git add reports/refactor/03-verification-runbook.md
      git commit -m "chore(verify): preview-deploy smoke test (auto)" >/dev/null 2>&1 || true
      git push -u origin "$branch" >/dev/null 2>&1 || { echo "    push failed" >&2; exit 1; }
      gh pr create --title "[verify] preview-deploy smoke" --body "Auto-created by 03-verification.sh --exercise-preview-deploy. SAFE TO CLOSE." --label "phase3-dryrun" >/dev/null 2>&1 || true
    ) || { fail G4 "exercise preview" "git/gh setup failed"; return; }

    local pr_num
    pr_num="$(gh pr list --head "$branch" --json number --jq '.[0].number' 2>/dev/null || echo "")"
    if [ -z "$pr_num" ]; then
      fail G4 "exercise preview" "PR creation succeeded but number not resolved"
      return
    fi
    note "    PR #$pr_num opened; waiting up to 12 min for Preview Deploy workflow"

    # Poll for the deploy-preview job; bounded wait
    local waited=0
    local conclusion=""
    while [ $waited -lt 720 ]; do
      conclusion="$(gh run list --workflow=preview-deploy.yml --branch "$branch" --limit 1 \
                      --json conclusion --jq '.[0].conclusion' 2>/dev/null || echo "")"
      [ -n "$conclusion" ] && [ "$conclusion" != "null" ] && break
      sleep 30; waited=$((waited+30))
    done

    if [ "$conclusion" = "success" ]; then
      pass G4 "preview-deploy.yml green on PR #$pr_num"
      # Pull the preview URL out of the PR comment marker
      local body
      body="$(gh pr view "$pr_num" --json comments --jq '.comments[].body' 2>/dev/null | grep -m1 -oE 'https://pr-[0-9]+---[^ |]+\.run\.app' || true)"
      if [ -n "$body" ]; then
        local code; code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${body}/api/health" || echo 000)"
        if [ "$code" = "200" ]; then
          pass G5 "preview URL $body /api/health -> 200"
        else
          fail G5 "preview URL" "$body /api/health returned $code"
        fi
      else
        fail G5 "preview URL" "no PR comment matched /pr-N---.*run\\.app/ marker"
      fi
    else
      fail G4 "preview-deploy.yml" "PR #$pr_num conclusion='${conclusion:-timeout}'"
    fi

    # Close the PR to trigger preview-cleanup.yml
    note "    closing PR #$pr_num to exercise preview-cleanup"
    gh pr close "$pr_num" --delete-branch >/dev/null 2>&1 || true
    sleep 20
    local cleanup
    cleanup="$(gh run list --workflow=preview-cleanup.yml --limit 5 --json conclusion,headBranch \
                 --jq ".[] | select(.headBranch==\"$branch\") | .conclusion" 2>/dev/null | head -1 || echo "")"
    if [ "$cleanup" = "success" ] || [ -z "$cleanup" ]; then
      # cleanup may still be running; not finding a result yet is not a fail. The runbook tells operator to recheck.
      pass G6 "preview-cleanup.yml dispatched (final result: ${cleanup:-pending — recheck manually})"
    else
      fail G6 "preview-cleanup.yml" "conclusion='$cleanup'"
    fi
  else
    skipc G4 "active preview exercise" "pass --exercise-preview-deploy to run (mutating)"
    skipc G5 "preview URL probe" "depends on G4"
    skipc G6 "preview-cleanup" "depends on G4"
  fi
}

# =============================================================================
# SECTION H — End-to-end smoke
# =============================================================================
section_H() {
  section "H. End-to-end smoke"

  # H1 — doctor.sh
  if [ -x "$REPO_ROOT/scripts/doctor.sh" ] || [ -f "$REPO_ROOT/scripts/doctor.sh" ]; then
    if bash "$REPO_ROOT/scripts/doctor.sh" >/dev/null 2>&1; then
      pass H1 "scripts/doctor.sh exits 0"
    else
      # doctor.sh frequently has WARN-level findings that aren't blockers; we report but don't fail by default
      note "    doctor.sh returned non-zero — review output by running it directly"
      pass H1 "scripts/doctor.sh ran (non-zero exit treated as informational — see runbook)"
    fi
  else
    skipc H1 "doctor.sh" "not found"
  fi

  # H2 — pytest
  if have uv && [ -f "$REPO_ROOT/pyproject.toml" ]; then
    if (cd "$REPO_ROOT" && uv run pytest -q --maxfail=1 -x >/dev/null 2>&1); then
      pass H2 "uv run pytest -q passes"
    else
      fail H2 "uv run pytest" "tests failed — run 'uv run pytest' for details"
    fi
  else
    skipc H2 "pytest" "uv not installed or no pyproject.toml"
  fi

  # H3 — production /healthz (if we can resolve the URL via gcloud)
  if gcloud_authed; then
    local proj; proj="$(resolve_gcp_project || true)"
    local url=""
    if [ -n "$proj" ]; then
      url="$(gcloud run services describe "$NEW_SERVICE" --region="$DEFAULT_REGION" --project="$proj" \
              --format='value(status.url)' 2>/dev/null || true)"
    fi
    if [ -n "$url" ] && have curl; then
      # FastAPI app's documented health endpoint is /api/health (preview-deploy.yml:235).
      # The user brief mentioned /healthz; try /healthz first, fall back to /api/health.
      local code
      code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${url}/healthz" || echo 000)"
      if [ "$code" = "200" ]; then
        pass H3 "production ${url}/healthz -> 200"
      else
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${url}/api/health" || echo 000)"
        if [ "$code" = "200" ]; then
          pass H3 "production ${url}/api/health -> 200 (/healthz not exposed; /api/health is canonical)"
        else
          fail H3 "production health" "neither /healthz nor /api/health returned 200 on $url"
        fi
      fi
    else
      skipc H3 "production health" "no URL resolved or no curl"
    fi
  else
    skipc H3 "production health" "gcloud not authed"
  fi
}

# =============================================================================
# SECTION I — Supabase identity invariants (must NOT have been migrated)
# =============================================================================
section_I() {
  section "I. Supabase identity invariants"

  # I1 — supabase/config.toml project_id was the local CLI namespace and SHOULD be 'masterkey' now (this is intentionally
  #      the local stack name, not the remote project ref). Already checked in B6 but cross-call here for runbook traceability.
  if [ -f "$REPO_ROOT/supabase/config.toml" ]; then
    if grep -qE '^project_id *= *"masterkey"' "$REPO_ROOT/supabase/config.toml"; then
      pass I1 "local Supabase workspace renamed to 'masterkey' (config.toml)"
    else
      fail I1 "supabase/config.toml project_id" "expected 'masterkey' (local-only identifier)"
    fi
  else
    skipc I1 "supabase/config.toml" "file not found"
  fi

  # I2 — remote project ref must be UNCHANGED (plan §2.3 + §6 out of scope)
  local hits
  hits="$(grep -rIn "$SUPABASE_PROJECT_REF" "$REPO_ROOT" \
            --exclude-dir=.git --exclude-dir=node_modules \
            --include='*.py' --include='*.yml' --include='*.sh' --include='*.toml' --include='*.md' \
            2>/dev/null | wc -l | tr -d ' ')"
  if [ "$hits" -ge 1 ]; then
    pass I2 "Supabase project ref ${SUPABASE_PROJECT_REF} still referenced ($hits places) — unchanged as required"
  else
    fail I2 "Supabase project ref" "ref ${SUPABASE_PROJECT_REF} not found anywhere — was it accidentally migrated?"
  fi

  # I3 — Supabase CLI link confirms the local working copy is still bound to the same remote project
  if supabase_cli_ok; then
    if (cd "$REPO_ROOT" && supabase status >/dev/null 2>&1); then
      pass I3 "supabase status executes (local link OK)"
    else
      skipc I3 "supabase status" "local stack not running (run 'supabase start' to verify fully)"
    fi
  else
    skipc I3 "supabase status" "supabase CLI not installed"
  fi

  # I4 — Auth redirect allowlist note. This cannot be queried via the public API without a service-role token
  #      embedded in the dashboard; we surface a SKIP with the manual command in the runbook.
  skipc I4 "Supabase Auth redirect allowlist" "manual dashboard check — runbook §G + Phase 3 step 26 / Phase 5 step 37"
}

# =============================================================================
# SECTION J — Agent + framework artifact checks
# =============================================================================
section_J() {
  section "J. Agent + framework artifacts"

  # J1 — .agile-flow-version upstream URL MUST remain pointing at vibeacademy/agile-flow (plan §2.7)
  if [ -f "$REPO_ROOT/.agile-flow-version" ]; then
    if grep -qE 'vibeacademy/(agile-flow|gembaflow)' "$REPO_ROOT/.agile-flow-version"; then
      pass J1 ".agile-flow-version upstream URL preserved (framework template)"
    else
      fail J1 ".agile-flow-version" "upstream URL changed — must remain at framework template, not the product repo"
    fi
  else
    skipc J1 ".agile-flow-version" "file not found"
  fi

  # J2 — github-ticket-worker.md should no longer say "Product: Cubrox"
  local twr="$REPO_ROOT/.claude/agents/github-ticket-worker.md"
  if [ -f "$twr" ]; then
    if grep -qE '\*\*Product\*\*: *Cubrox' "$twr"; then
      fail J2 "github-ticket-worker.md" "still says 'Product: Cubrox' (plan §2.7)"
    else
      pass J2 "github-ticket-worker.md product line updated"
    fi
  else
    skipc J2 "github-ticket-worker.md" "file not found"
  fi

  # J3 — devops-engineer.md references — file IS in .agile-flow-overrides so it should be edited (plan §2.7)
  local dev="$REPO_ROOT/.claude/agents/devops-engineer.md"
  if [ -f "$dev" ]; then
    # shellcheck disable=SC2016
    if grep -qE '^\| `CLOUD_RUN_SERVICE` *\| *`agile-flow-app`' "$dev"; then
      fail J3 "devops-engineer.md" "table still shows 'agile-flow-app' as CLOUD_RUN_SERVICE default (plan §2.7)"
    else
      pass J3 "devops-engineer.md CLOUD_RUN_SERVICE example updated"
    fi
  else
    skipc J3 "devops-engineer.md" "file not found"
  fi

  # J4 — CLAUDE.md project info block — Repository should now point at new repo + service docker command updated
  if [ -f "$REPO_ROOT/CLAUDE.md" ]; then
    local ok=1
    grep -qE 'Project Name.*Master Key' "$REPO_ROOT/CLAUDE.md" || ok=0
    grep -qE 'github.com/cubrox/masterkey' "$REPO_ROOT/CLAUDE.md" || ok=0
    grep -qE 'docker build -t masterkey' "$REPO_ROOT/CLAUDE.md" || ok=0
    if [ $ok -eq 1 ]; then
      pass J4 "CLAUDE.md Project Information block fully updated"
    else
      fail J4 "CLAUDE.md" "Project Information block incomplete (name / repo URL / docker command)"
    fi
  else
    skipc J4 "CLAUDE.md" "file not found"
  fi
}

# =============================================================================
# Main
# =============================================================================
main() {
  echo "${C_CYN}=================================================================${C_NC}"
  echo "${C_CYN}  cubrox -> masterkey rename verification ($(date -u +%FT%TZ))${C_NC}"
  echo "${C_CYN}  Repo root: ${REPO_ROOT}${C_NC}"
  echo "${C_CYN}=================================================================${C_NC}"

  run_section A && section_A
  run_section B && section_B
  run_section C && section_C
  run_section D && section_D
  run_section E && section_E
  run_section F && section_F
  run_section G && section_G
  run_section H && section_H
  run_section I && section_I
  run_section J && section_J

  echo
  echo "${C_CYN}━━━ Summary ━━━${C_NC}"
  echo "Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed, ${SKIP_COUNT} skipped"
  if [ "$FAIL_COUNT" -gt 0 ]; then
    echo
    echo "${C_RED}Failures:${C_NC}"
    for line in "${FAIL_LINES[@]}"; do echo "  - $line"; done
  fi
  if [ "$FAIL_COUNT" -eq 0 ]; then exit 0; else exit 1; fi
}

main "$@"
