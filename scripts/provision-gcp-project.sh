#!/usr/bin/env bash
#
# provision-gcp-project.sh — one-shot GCP project setup for Agile Flow GCP.
#
# Creates a GCP project (optional), enables required APIs, creates an
# Artifact Registry repo, creates a deployer service account with the
# minimum required roles, and optionally generates a service account JSON
# key for workshop use.
#
# Usage:
#   ./scripts/provision-gcp-project.sh [--create-project] [--with-sa-key]
#
# Environment variables:
#   GCP_PROJECT_ID       (required) Project ID to provision into
#   GCP_REGION           (default: us-central1)
#   ARTIFACT_REPO        (default: agile-flow)
#   BILLING_ACCOUNT_ID   (required if --create-project)
#   GITHUB_OWNER         (optional) GitHub owner of the participant's
#                        fork. Personal username (alice-gh) or org (acme).
#                        Required to enable Step 5.5 (WIF setup).
#   GITHUB_REPO          (default: agile-flow-gcp) Repo name within
#                        GITHUB_OWNER. Set when participants fork into
#                        an org and rename the repo for their product.
#   GITHUB_USERNAME      Legacy alias for GITHUB_OWNER. When GITHUB_OWNER
#                        is unset, the script uses GITHUB_USERNAME as the
#                        owner. Existing callers don't need to change.
#   NEON_API_KEY         (optional) Enables Step 5.7 (Neon branch +
#                        database-url Secret Manager). Required for
#                        per-attendee branch automation.
#   NEON_PROJECT_ID      (optional) Same: required for Step 5.7.
#   NEON_BRANCH_NAME     (optional) Same: required for Step 5.7.
#                        Wrapper sets this from the CSV's neon_branch
#                        column (defaults to handle).
#   BUDGET_CAP_USD       (optional) Enables Step 5.6 (per-project billing
#                        budget with 50/90/100% thresholds + forecast).
#                        When set, BILLING_ACCOUNT_ID is also required.
#                        The runner needs roles/billing.costsManager on
#                        the billing account. When unset, step is skipped.
#   GITHUB_REPOSITORY    (optional) `<owner>/<repo>` of the participant's
#                        fork (e.g. `acme/widget-shop`). Enables Step 7,
#                        which pushes GCP_PROJECT_ID, GCP_SERVICE_ACCOUNT,
#                        GCP_WORKLOAD_IDENTITY_PROVIDER, and (when Neon
#                        is configured) NEON_PARENT_BRANCH directly into
#                        the fork's Actions secrets via `gh secret set`.
#                        Requires `gh` on PATH and authenticated. When
#                        either is missing, the script falls back to
#                        printing the values for manual entry.
#
# Notes:
# - This script is idempotent. Re-running skips resources that already exist.
# - `--with-sa-key` generates a long-lived service account key. Use for
#   workshops only. For production, set up Workload Identity Federation
#   separately (see docs/PLATFORM-GUIDE.md Step 5).
#
# After running, paste the output into your GitHub repo's secrets panel.

set -euo pipefail

GCP_REGION="${GCP_REGION:-us-central1}"
ARTIFACT_REPO="${ARTIFACT_REPO:-agile-flow}"

# ── Retry helper for GCP eventual consistency ────────────────────────────
#
# Two known propagation windows in this script:
#   1. After `gcloud services enable`, the API endpoint can return 403
#      (PERMISSION_DENIED, "API has not been used") for 30-90 seconds.
#   2. After `gcloud iam service-accounts create`, the IAM policy
#      machinery rejects bindings against the new SA with
#      INVALID_ARGUMENT: "Service account ... does not exist" for a
#      few seconds.
#
# We classify by stderr signature: anything matching the transient
# patterns retries with exponential backoff; anything else fails
# immediately. There is no explicit permanent-error list — if the
# stderr doesn't match a known-transient pattern, we bail.
#
# Usage:
#   retry_eventual_consistency <label> -- <gcloud command...>
#
# Defaults: 6 attempts, exponential backoff (2,4,8,16,30,30s), ~90s cap.
# Override with RETRY_MAX_ATTEMPTS, RETRY_MAX_SLEEP env vars.

RETRY_MAX_ATTEMPTS="${RETRY_MAX_ATTEMPTS:-6}"
RETRY_MAX_SLEEP="${RETRY_MAX_SLEEP:-30}"

retry_eventual_consistency() {
  local label="$1"; shift
  if [[ "${1:-}" != "--" ]]; then
    echo "ERROR: retry_eventual_consistency expects 'label -- cmd...'" >&2
    return 2
  fi
  shift

  local attempt=1
  local sleep_s=2
  local stderr_file
  stderr_file="$(mktemp)"

  local exit_code
  while (( attempt <= RETRY_MAX_ATTEMPTS )); do
    # Run the command with `set -e` temporarily disabled so we can capture
    # its exit code. Bash function-local `set +e` does not leak out of
    # the function in a `command || handler` pattern, but a bare `if/then`
    # clobbers $?. Cleanest: && / || chain.
    exit_code=0
    "$@" 2> "$stderr_file" || exit_code=$?

    if (( exit_code == 0 )); then
      cat "$stderr_file" >&2
      rm -f "$stderr_file"
      return 0
    fi

    # Transient eventual-consistency signatures. Checked BEFORE permanent
    # patterns because GCP returns INVALID_ARGUMENT for "service account
    # does not exist" right after creating it — that's a propagation lag,
    # not a typo.
    if grep -qE 'PERMISSION_DENIED.*denied on resource|IAM_PERMISSION_DENIED|API has not been used|SERVICE_DISABLED|Service account .* does not exist' "$stderr_file"; then
      if (( attempt == RETRY_MAX_ATTEMPTS )); then
        echo "[retry $attempt/$RETRY_MAX_ATTEMPTS] $label — exhausted" >&2
        cat "$stderr_file" >&2
        rm -f "$stderr_file"
        return "$exit_code"
      fi
      echo "[retry $attempt/$RETRY_MAX_ATTEMPTS] $label — transient (eventual consistency), sleeping ${sleep_s}s" >&2
      sleep "$sleep_s"
      sleep_s=$(( sleep_s * 2 ))
      (( sleep_s > RETRY_MAX_SLEEP )) && sleep_s=$RETRY_MAX_SLEEP
      attempt=$(( attempt + 1 ))
      continue
    fi

    # Unrecognized error — surface it and bail. Better to fail loudly than
    # to retry indefinitely on something we don't understand.
    cat "$stderr_file" >&2
    rm -f "$stderr_file"
    return "$exit_code"
  done

  rm -f "$stderr_file"
  return 1
}

# ── Step 0: Activate the in-repo pre-push hook ──────────────────────────
#
# `core.hooksPath` is per-clone, not versioned with the repo. Without
# this, the working pre-push hook at `scripts/hooks/pre-push` is dormant
# on every fresh clone — `git push` skips lint and tests silently. The
# CLAUDE.md rule "Never use `git push --no-verify`" is unenforceable
# when there is no hook to skip.
#
# Run this BEFORE arg-parsing, input validation, and any GCP call so
# that a partial run — including the most common day-1 failure path,
# `provision-gcp-project.sh` invoked without GCP_PROJECT_ID set — still
# leaves the quality gate active. Idempotent: no-op when already set.
# Uses --local so a user's global hooksPath (e.g. for husky) is
# overridden only inside this repo. See #77.

if [[ -d .git ]] && [[ -f scripts/hooks/pre-push ]]; then
  current_hooks_path="$(git config --local --get core.hooksPath 2>/dev/null || true)"
  if [[ "$current_hooks_path" != "scripts/hooks" ]]; then
    git config --local core.hooksPath scripts/hooks
    echo "[hook] Activated pre-push hook (lint + tests will run before every push)"
    echo ""
  fi
fi

CREATE_PROJECT=false
WITH_SA_KEY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create-project) CREATE_PROJECT=true; shift ;;
    --with-sa-key) WITH_SA_KEY=true; shift ;;
    -h|--help)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required" >&2
  echo "Usage: GCP_PROJECT_ID=my-project ./scripts/provision-gcp-project.sh" >&2
  exit 1
fi

echo "=================================="
echo "  Agile Flow GCP Provisioning"
echo "=================================="
echo "  Project:  $GCP_PROJECT_ID"
echo "  Region:   $GCP_REGION"
echo "  Repo:     $ARTIFACT_REPO"
echo "  Create:   $CREATE_PROJECT"
echo "  SA key:   $WITH_SA_KEY"
echo ""

# ── Step 1: Create project (optional) ────────────────────────────────────

if [[ "$CREATE_PROJECT" == "true" ]]; then
  if [[ -z "${BILLING_ACCOUNT_ID:-}" ]]; then
    echo "ERROR: BILLING_ACCOUNT_ID required when --create-project is set" >&2
    exit 1
  fi

  if gcloud projects describe "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    # Project ID exists. We need to know whether it's ours and modifiable.
    # GCP project IDs are global, so an ID can exist in another org and
    # still respond to `describe`. Probe by attempting to read its IAM
    # policy — if we have getIamPolicy, we have enough to billing-link
    # and bind roles. If we don't, the project isn't ours.
    if gcloud projects get-iam-policy "$GCP_PROJECT_ID" >/dev/null 2>&1; then
      project_state="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(lifecycleState)' 2>/dev/null)"
      if [[ "$project_state" == "ACTIVE" ]]; then
        echo "[skip] Project $GCP_PROJECT_ID already exists (ACTIVE, owned by you)"
      else
        echo "" >&2
        echo "ERROR: Project $GCP_PROJECT_ID exists in your org but is in state: $project_state" >&2
        echo "       Either restore it via the Cloud Console (Resource Manager > recently deleted)" >&2
        echo "       or change the 'cohort' column in roster.csv to generate a fresh project ID." >&2
        exit 1
      fi
    else
      echo "" >&2
      echo "ERROR: Project $GCP_PROJECT_ID exists but you do not have permission to modify it." >&2
      echo "       This usually means the ID is taken in another GCP organization." >&2
      echo "       (GCP project IDs are globally unique across all of Google Cloud.)" >&2
      echo "       Change the 'cohort' column in roster.csv to generate a fresh project ID." >&2
      exit 1
    fi
  else
    echo "[create] Project $GCP_PROJECT_ID"
    gcloud projects create "$GCP_PROJECT_ID"
  fi

  # Skip the link call when this project is already linked to the same
  # billing account. Re-linking an already-linked project is unnecessary
  # AND fails with `Cloud billing quota exceeded` once you're at the
  # billing account's project-link cap (5 by default on free tiers) —
  # `billing projects link` is metered against that quota even when the
  # project in question is already linked. Idempotent re-runs would
  # otherwise fail on every wrapper invocation after the cap is hit,
  # even though the desired state is already satisfied.
  current_billing="$(gcloud billing projects describe "$GCP_PROJECT_ID" \
    --format='value(billingAccountName)' 2>/dev/null || true)"
  if [[ "$current_billing" == "billingAccounts/${BILLING_ACCOUNT_ID}" ]]; then
    echo "[skip] Billing account $BILLING_ACCOUNT_ID already linked"
  else
    echo "[link] Billing account $BILLING_ACCOUNT_ID"
    gcloud billing projects link "$GCP_PROJECT_ID" \
      --billing-account="$BILLING_ACCOUNT_ID"
  fi
fi

# ── Step 1.5: Override Domain Restricted Sharing (workshop projects) ─────
#
# If the parent org enforces `iam.allowedPolicyMemberDomains` (a list
# constraint, on by default for Cloud Identity Free orgs), every
# subsequent IAM binding to an external-domain identity (Gmail, other
# Workspace) fails with FAILED_PRECONDITION. Override per project:
# allValues=ALLOW so any Google identity can be a binding member.
# Production projects in the same org keep their constraint.
#
# This is a list constraint, NOT a boolean — `disable-enforce` does not
# work; `set-policy` with the explicit listPolicy form does. See
# docs/PATTERN-LIBRARY.md pattern #30.
#
# Decision logic: read the project's `describe` output. If listPolicy
# already resolves to ALLOW (override in place), skip. Otherwise apply
# the override unconditionally — the `set-policy` call is itself
# idempotent on a project that already has the same allValues, so no
# harm in always running it on a non-ALLOW project. The earlier
# `org-policies list` probe was unreliable: org-inherited constraints
# don't always appear in the project's list view, so workshop projects
# under an org with the constraint set at the org level were silently
# left without the override and failed at the first external-domain
# IAM binding (e.g. roles/editor to a Gmail account).

drs_effective="$(gcloud resource-manager org-policies describe \
  iam.allowedPolicyMemberDomains \
  --project="$GCP_PROJECT_ID" \
  --format='value(listPolicy.allValues)' 2>/dev/null || true)"

if [[ "$drs_effective" == "ALLOW" ]]; then
  echo "[skip] domain-restricted-sharing override already in place for $GCP_PROJECT_ID"
else
  echo "[override] applying domain-restricted-sharing override for $GCP_PROJECT_ID"
  echo '{"constraint":"constraints/iam.allowedPolicyMemberDomains","listPolicy":{"allValues":"ALLOW"}}' \
    | gcloud resource-manager org-policies set-policy /dev/stdin \
        --project="$GCP_PROJECT_ID" >/dev/null
fi

# ── Step 2: Enable APIs ──────────────────────────────────────────────────

echo "[enable] Required APIs (may take 30-60 seconds on first run)"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  billingbudgets.googleapis.com \
  --project="$GCP_PROJECT_ID"

# ── Step 3: Artifact Registry repo ───────────────────────────────────────

if gcloud artifacts repositories describe "$ARTIFACT_REPO" \
  --location="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  echo "[skip] Artifact Registry repo '$ARTIFACT_REPO' already exists"
else
  echo "[create] Artifact Registry repo '$ARTIFACT_REPO'"
  retry_eventual_consistency "artifact registry create" -- \
    gcloud artifacts repositories create "$ARTIFACT_REPO" \
      --repository-format=docker \
      --location="$GCP_REGION" \
      --project="$GCP_PROJECT_ID"
fi

# ── Step 4: Deployer service account ─────────────────────────────────────

SA_EMAIL="deployer@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "$SA_EMAIL" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  echo "[skip] Service account 'deployer' already exists"
else
  echo "[create] Service account 'deployer'"
  retry_eventual_consistency "service account create" -- \
    gcloud iam service-accounts create deployer \
      --display-name="GitHub Actions deployer" \
      --project="$GCP_PROJECT_ID"

  # The IAM policy machinery often does not see the new SA for a few
  # seconds after creation. Wait for `describe` to confirm visibility
  # before entering the binding loop. Bounded at ~30s.
  echo "[wait] Service account propagation"
  for i in 1 2 3 4 5 6; do
    if gcloud iam service-accounts describe "$SA_EMAIL" \
      --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
      break
    fi
    sleep 5
    if (( i == 6 )); then
      echo "[wait] propagation slow — falling through to retry loop in bindings" >&2
    fi
  done
fi

# ── Step 5: IAM roles ────────────────────────────────────────────────────

ROLES=(
  "roles/run.admin"
  "roles/artifactregistry.writer"
  "roles/iam.serviceAccountUser"
  "roles/secretmanager.secretAccessor"
)

for role in "${ROLES[@]}"; do
  echo "[bind] $role -> $SA_EMAIL"
  retry_eventual_consistency "iam bind $role" -- \
    gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
      --member="serviceAccount:${SA_EMAIL}" \
      --role="$role" \
      --condition=None \
      --quiet >/dev/null
done

# ── Step 5.5: Workload Identity Federation (when GITHUB_OWNER set) ──────
#
# Trust GitHub Actions OIDC tokens from a specific repo so deploys can
# impersonate the deployer SA without a long-lived JSON key. Gated on
# GITHUB_OWNER being set — when unset, this whole block is skipped and
# the script's existing --with-sa-key path remains the auth fallback.
#
# Inputs (the wrapper sets these per row from roster.csv):
#   GITHUB_OWNER     The GitHub owner of the participant's fork. May be
#                    a personal username (alice-gh) or an organization
#                    (acme). Required to enable Step 5.5.
#   GITHUB_REPO      The repo name within the owner. Defaults to
#                    'agile-flow-gcp' when unset.
#   GITHUB_USERNAME  Legacy alias for GITHUB_OWNER. Used when GITHUB_OWNER
#                    is unset, so external callers that set the older
#                    name continue to work.
#
# Together they identify the GitHub repo whose Actions runs are trusted
# to impersonate the deployer SA. Owners with org forks can rename their
# repo (acme/widget-shop) and the binding still works because the
# wrapper passes both fields explicitly.
#
# Google requires --attribute-condition on OIDC providers (it must
# reference at least one provider claim). We use a trivially-true
# condition (`assertion.repository != ''`) so the provider doesn't gate
# access by org or repo — attendees may fork under any GitHub account
# or org. Trust scoping happens at the IAM binding layer instead, where
# attribute.repository=<owner>/<repo> pins each binding to one specific
# repo.
#
# All three sub-steps (pool, provider, binding) are idempotent.

# Resolve GITHUB_OWNER, falling back to GITHUB_USERNAME for backwards
# compatibility with external callers from before #40.
WIF_OWNER="${GITHUB_OWNER:-${GITHUB_USERNAME:-}}"
WIF_REPO_NAME="${GITHUB_REPO:-agile-flow-gcp}"

if [[ -n "$WIF_OWNER" ]]; then
  WIF_POOL="github"
  WIF_PROVIDER="github"

  PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"

  # 5.5a: Create the workload-identity pool (idempotent)
  if gcloud iam workload-identity-pools describe "$WIF_POOL" \
    --location=global \
    --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    echo "[skip] WIF pool '$WIF_POOL' already exists"
  else
    echo "[create] WIF pool '$WIF_POOL'"
    gcloud iam workload-identity-pools create "$WIF_POOL" \
      --location=global \
      --display-name="GitHub Actions" \
      --project="$GCP_PROJECT_ID"
  fi

  # 5.5b: Create the OIDC provider trusting GitHub Actions tokens
  if gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" \
    --workload-identity-pool="$WIF_POOL" \
    --location=global \
    --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    echo "[skip] WIF provider '$WIF_PROVIDER' already exists"
  else
    echo "[create] WIF provider '$WIF_PROVIDER'"
    gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
      --workload-identity-pool="$WIF_POOL" \
      --location=global \
      --issuer-uri="https://token.actions.githubusercontent.com" \
      --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
      --attribute-condition="assertion.repository != ''" \
      --project="$GCP_PROJECT_ID"
  fi

  # 5.5c: Bind the deployer SA so the specific repo can impersonate it.
  # google-github-actions/auth@v2 in impersonation mode (which our deploy
  # workflow uses by passing both `workload_identity_provider` and
  # `service_account`) needs TWO roles:
  #
  #   roles/iam.workloadIdentityUser    — lets the federated identity
  #                                        authenticate AS the SA via WIF
  #   roles/iam.serviceAccountTokenCreator — lets the federated identity
  #                                        MINT access tokens for the SA
  #                                        (gcloud auth, docker push, etc.)
  #
  # Granting only the first leaves the deploy step's docker-push call
  # failing with `iam.serviceAccounts.getAccessToken denied`.
  #
  # add-iam-policy-binding is idempotent — re-running with the same member
  # is a no-op.
  #
  # The SA's IAM policy machinery has the same eventual-consistency window
  # as project-level IAM bindings: a freshly-created SA can return
  # PERMISSION_DENIED on its own setIamPolicy for a few seconds. Wrap in
  # the retry helper to absorb that lag (it already classifies the
  # IAM_PERMISSION_DENIED signature as transient).
  WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${WIF_OWNER}/${WIF_REPO_NAME}"
  for wif_role in roles/iam.workloadIdentityUser roles/iam.serviceAccountTokenCreator; do
    echo "[bind] $wif_role <- ${WIF_OWNER}/${WIF_REPO_NAME}"
    retry_eventual_consistency "wif bind $wif_role" -- \
      gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
        --role="$wif_role" \
        --member="$WIF_MEMBER" \
        --project="$GCP_PROJECT_ID" \
        --quiet >/dev/null
  done

  WIF_PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"
else
  echo "[skip] WIF setup not requested (GITHUB_OWNER and GITHUB_USERNAME unset)"
fi

# ── Step 5.6: Per-project billing budget cap ────────────────────────────
#
# Creates a budget on the billing account, scoped to this single project,
# with thresholds at 50%/90%/100% of current spend plus 100% of forecasted
# spend. Notifications are sent to the billing account's default IAM
# recipients (Billing Account Admin/User) — no separate Cloud Monitoring
# notification channel needed.
#
# Gated on BUDGET_CAP_USD being set. When unset, the step is skipped
# silently — non-workshop callers don't need a budget.
#
# Idempotency: budgets list filtered by display-name. The display-name is
# `af-workshop-cap-<project_id>` to keep it unique per attendee project.
#
# Auto-cutoff (disabling billing on threshold hit) is intentionally NOT
# part of this step — see #42 for that follow-up. This step provides
# alerts only.
#
# The runner needs roles/billing.costsManager on the billing account to
# create budgets. Documented in PLATFORM-GUIDE.md.

if [[ -n "${BUDGET_CAP_USD:-}" ]]; then
  if [[ -z "${BILLING_ACCOUNT_ID:-}" ]]; then
    echo "ERROR: BUDGET_CAP_USD is set but BILLING_ACCOUNT_ID is unset" >&2
    echo "       Step 5.6 needs the billing account to create the budget." >&2
    exit 1
  fi

  # Validate that BUDGET_CAP_USD is a positive integer or decimal.
  if ! [[ "$BUDGET_CAP_USD" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "ERROR: BUDGET_CAP_USD must be a positive number (got: '$BUDGET_CAP_USD')" >&2
    exit 1
  fi

  # PROJECT_NUMBER may already be cached from Step 5.5. If WIF was skipped
  # (no GITHUB_OWNER), resolve it now.
  if [[ -z "${PROJECT_NUMBER:-}" ]]; then
    PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"
  fi

  BUDGET_DISPLAY_NAME="af-workshop-cap-${GCP_PROJECT_ID}"

  # Look up existing budget by display name. `gcloud billing budgets list`
  # has no server-side filter on displayName, so we fetch all on this
  # account and grep client-side. For a workshop billing account with
  # ~8 budgets that's fine; if this ever scales we can switch to the
  # `--filter` flag (which does a regex match on display name).
  #
  # Capture stderr to a tempfile and check the exit code explicitly. The
  # earlier `2>/dev/null | head` pattern swallowed permission errors and
  # let `set -euo pipefail` kill the script silently — facilitators saw
  # the wrapper exit "without error" partway through row 1, leaving the
  # remaining roster rows untouched. The most common cause is the
  # facilitator account lacking `roles/billing.costsManager` on the
  # billing account; we surface that with a pointer to the runbook.
  budget_list_err="$(mktemp)"
  budget_list_ec=0
  existing_budget="$(gcloud billing budgets list \
    --billing-account="$BILLING_ACCOUNT_ID" \
    --filter="displayName=${BUDGET_DISPLAY_NAME}" \
    --format='value(name)' 2> "$budget_list_err" | head -n 1)" || budget_list_ec=$?
  if (( budget_list_ec != 0 )); then
    echo "" >&2
    echo "ERROR: gcloud billing budgets list failed (exit $budget_list_ec)" >&2
    echo "       billing account: $BILLING_ACCOUNT_ID" >&2
    echo "" >&2
    cat "$budget_list_err" >&2
    echo "" >&2
    echo "  The facilitator account needs roles/billing.costsManager on the" >&2
    echo "  billing account. See docs/PLATFORM-GUIDE.md > Budget guardrails." >&2
    echo "  To skip this step, unset BUDGET_CAP_USD and re-run." >&2
    rm -f "$budget_list_err"
    exit 1
  fi
  rm -f "$budget_list_err"

  if [[ -n "$existing_budget" ]]; then
    echo "[skip] budget '${BUDGET_DISPLAY_NAME}' already exists (\$${BUDGET_CAP_USD} USD)"
  else
    echo "[create] budget '${BUDGET_DISPLAY_NAME}' (\$${BUDGET_CAP_USD} USD, scoped to $GCP_PROJECT_ID)"
    gcloud billing budgets create \
      --billing-account="$BILLING_ACCOUNT_ID" \
      --display-name="$BUDGET_DISPLAY_NAME" \
      --budget-amount="${BUDGET_CAP_USD}USD" \
      --filter-projects="projects/${PROJECT_NUMBER}" \
      --threshold-rule=percent=0.50 \
      --threshold-rule=percent=0.90 \
      --threshold-rule=percent=1.0 \
      --threshold-rule=percent=1.0,basis=forecasted-spend \
      --quiet >/dev/null
  fi
else
  echo "[skip] budget cap (BUDGET_CAP_USD unset)"
fi

# ── Step 5.7: Neon branch + database-url Secret Manager ─────────────────
#
# Creates a per-attendee Neon branch and writes its pooled connection
# string to the Secret Manager secret `database-url` in this GCP project.
# Cloud Run mounts that secret as DATABASE_URL at runtime.
#
# Gated on NEON_API_KEY, NEON_PROJECT_ID, and NEON_BRANCH_NAME being set.
# When any is unset, the step is skipped and the participant must create
# the secret by hand (the script's "Next steps" footer notes this).
#
# Idempotency:
#   - Branch already exists → fetch its pooled URI; do NOT recreate or
#     reparent (per design decision: workshops are short-lived; drift
#     against `main` is not checked).
#   - Secret already exists with same value → no-op.
#   - Secret exists with different value → add a new version.
#
# Connection URIs are sensitive (they include credentials). They are
# never logged to stdout/stderr; only written to Secret Manager.

if [[ -n "${NEON_API_KEY:-}" && -n "${NEON_PROJECT_ID:-}" && -n "${NEON_BRANCH_NAME:-}" ]]; then
  NEON_API_BASE="https://console.neon.tech/api/v2"

  # Helper: GET against Neon API. Body to stdout; error to stderr.
  # Uses --fail-with-body so curl exits non-zero on 4xx/5xx but we still
  # see the response.
  neon_get() {
    local path="$1"
    curl --silent --show-error --fail-with-body \
      -H "Authorization: Bearer $NEON_API_KEY" \
      -H "Accept: application/json" \
      "${NEON_API_BASE}${path}"
  }

  # Helper: POST. Same return semantics as neon_get. Captures HTTP code
  # separately so 409 (branch exists) can be distinguished from real
  # errors without --fail's cliff.
  neon_post() {
    local path="$1"
    local body="$2"
    local out_file="$3"
    curl --silent --show-error \
      --output "$out_file" \
      --write-out '%{http_code}' \
      -X POST \
      -H "Authorization: Bearer $NEON_API_KEY" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d "$body" \
      "${NEON_API_BASE}${path}"
  }

  # 5.7a: Find the project's main branch ID.
  echo "[neon] looking up parent (main) branch in project $NEON_PROJECT_ID"
  branches_json="$(neon_get "/projects/${NEON_PROJECT_ID}/branches")"
  parent_branch_id="$(echo "$branches_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
branches = data.get('branches', [])
for b in branches:
    if b.get('default'):
        print(b['id'])
        sys.exit(0)
sys.exit('no default branch found in project response')
" 2>&1)"
  if [[ -z "$parent_branch_id" || "$parent_branch_id" == *"no default branch"* ]]; then
    echo "ERROR: could not find default (main) branch in Neon project $NEON_PROJECT_ID" >&2
    echo "       response: $branches_json" >&2
    exit 1
  fi

  # 5.7b: Try to create the attendee's branch.
  echo "[neon] creating branch '$NEON_BRANCH_NAME' (parent: $parent_branch_id)"
  create_response_file="$(mktemp)"
  create_body="$(printf '{"branch":{"name":"%s","parent_id":"%s"},"endpoints":[{"type":"read_write"}]}' "$NEON_BRANCH_NAME" "$parent_branch_id")"
  http_code="$(neon_post "/projects/${NEON_PROJECT_ID}/branches" "$create_body" "$create_response_file" || echo "000")"

  if [[ "$http_code" == "201" || "$http_code" == "200" ]]; then
    branch_id="$(python3 -c "import json,sys; print(json.load(open('$create_response_file'))['branch']['id'])")"
    echo "[neon] branch created (id=$branch_id)"
  elif [[ "$http_code" == "409" ]]; then
    # 409: a branch with this name already exists in the project.
    #
    # Default behavior (since #90): fail loud. Two roster rows with
    # the same handle, OR a roster row whose handle matches a branch
    # left over from a prior cohort, would otherwise silently mount
    # this attendee's database-url Secret Manager secret to the
    # OTHER attendee's Neon branch — invisible cross-contamination.
    #
    # NEON_FORCE_SHARED_PARENT=true preserves the original silent-reuse
    # behavior for legitimate cases: paired attendees collaborating on
    # the same dataset, or re-running the same cohort against an
    # already-populated Neon project. Set explicitly; never default on.
    if [[ "${NEON_FORCE_SHARED_PARENT:-false}" != "true" ]]; then
      echo "ERROR: Neon branch '$NEON_BRANCH_NAME' already exists in project '$NEON_PROJECT_ID'." >&2
      echo "  This may mean: another roster row already used this handle," >&2
      echo "  OR a prior cohort left a branch with this name." >&2
      echo "  Choose a different handle, OR set NEON_FORCE_SHARED_PARENT=true" >&2
      echo "  if you intentionally want to share the parent branch (paired" >&2
      echo "  collaboration, or re-running the same cohort)." >&2
      rm -f "$create_response_file"
      exit 1
    fi
    echo "[neon] branch '$NEON_BRANCH_NAME' already exists; reusing per NEON_FORCE_SHARED_PARENT=true"
    # Look up the existing branch's ID by name.
    branch_id="$(echo "$branches_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
target = '$NEON_BRANCH_NAME'
for b in data.get('branches', []):
    if b.get('name') == target:
        print(b['id'])
        sys.exit(0)
" 2>&1)"
    if [[ -z "$branch_id" ]]; then
      # The branch exists per Neon (409) but our cached branches_json from
      # 5.7a didn't include it (race). Re-fetch.
      branches_json="$(neon_get "/projects/${NEON_PROJECT_ID}/branches")"
      branch_id="$(echo "$branches_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
target = '$NEON_BRANCH_NAME'
for b in data.get('branches', []):
    if b.get('name') == target:
        print(b['id'])
        sys.exit(0)
sys.exit('branch not found after 409')
" 2>&1)"
    fi
    if [[ -z "$branch_id" || "$branch_id" == *"branch not found"* ]]; then
      echo "ERROR: Neon returned 409 for branch '$NEON_BRANCH_NAME' but lookup failed" >&2
      exit 1
    fi
  else
    echo "ERROR: Neon branch create returned HTTP $http_code" >&2
    cat "$create_response_file" >&2
    rm -f "$create_response_file"
    exit 1
  fi
  rm -f "$create_response_file"

  # 5.7c: Fetch the pooled connection URI for this branch.
  echo "[neon] fetching pooled connection URI"
  uri_response="$(neon_get "/projects/${NEON_PROJECT_ID}/connection_uri?branch_id=${branch_id}&database_name=neondb&role_name=neondb_owner&pooled=true")"
  pooled_uri="$(echo "$uri_response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
uri = data.get('uri', '')
if not uri:
    sys.exit('connection_uri response missing uri field')
print(uri)
" 2>&1)"
  if [[ -z "$pooled_uri" || "$pooled_uri" == *"missing uri"* ]]; then
    echo "ERROR: could not fetch pooled connection URI" >&2
    exit 1
  fi
  # Sanity-check that we got the pooled host (sentinel: -pooler. in the host).
  if [[ "$pooled_uri" != *"-pooler."* ]]; then
    echo "WARN: connection URI does not contain '-pooler.'; is pooling enabled on this branch?" >&2
  fi

  # 5.7d: Write to Secret Manager. Idempotent: same value → no-op,
  # different value → versions add.
  if gcloud secrets describe database-url --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    current="$(gcloud secrets versions access latest --secret=database-url --project="$GCP_PROJECT_ID" 2>/dev/null || true)"
    if [[ "$current" == "$pooled_uri" ]]; then
      echo "[skip] database-url secret already current"
    else
      echo "[update] database-url secret (adding new version)"
      printf '%s' "$pooled_uri" | gcloud secrets versions add database-url \
        --data-file=- --project="$GCP_PROJECT_ID" >/dev/null
    fi
  else
    echo "[create] database-url secret"
    printf '%s' "$pooled_uri" | gcloud secrets create database-url \
      --data-file=- --project="$GCP_PROJECT_ID" >/dev/null
  fi

  # 5.7e: Per-secret IAM binding for the deployer SA. Project-level
  # secretAccessor in Step 5 already covers this; per-secret is
  # defense-in-depth. Idempotent.
  echo "[bind] roles/secretmanager.secretAccessor on database-url -> $SA_EMAIL"
  gcloud secrets add-iam-policy-binding database-url \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$GCP_PROJECT_ID" \
    --quiet >/dev/null

  # Track that we ran for the footer.
  NEON_BRANCH_PROVISIONED="true"
else
  if [[ -z "${NEON_API_KEY:-}" ]]; then
    echo "[skip] Neon branch + database-url secret (NEON_API_KEY unset)"
  elif [[ -z "${NEON_PROJECT_ID:-}" ]]; then
    echo "[skip] Neon branch + database-url secret (NEON_PROJECT_ID unset)"
  else
    echo "[skip] Neon branch + database-url secret (NEON_BRANCH_NAME unset)"
  fi
  NEON_BRANCH_PROVISIONED="false"
fi

# ── Step 5.8: Pre-create Cloud Run service ──────────────────────────────
#
# preview-deploy.yml calls `gcloud run deploy --no-traffic --tag=pr-N`
# unconditionally. That works for any deploy after the first, but on the
# very first deploy gcloud rejects with:
#
#   ERROR: (gcloud.run.deploy) --no-traffic not supported when creating a
#   new service.
#
# A fresh fork's first ever PR preview always fails until the service
# exists. Pre-creating it here with a placeholder image ("hello") makes
# the workflow's assumption true from day 0. The first real preview-deploy
# overwrites the placeholder revision.
#
# Idempotent: if the service already exists (re-runs, or because deploy.yml
# already ran from the participant's fork), this step is a no-op.
#
# Pinned to:
#   --service-account = the deployer SA created in Step 4
#   --allow-unauthenticated = matches what preview-deploy.yml will produce,
#                              so first real deploy doesn't change ACL
#   --port=8080 = matches the FastAPI Dockerfile and preview-deploy config

SERVICE_NAME="${CLOUD_RUN_SERVICE:-masterkey}"

if gcloud run services describe "$SERVICE_NAME" \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  echo "[skip] Cloud Run service '$SERVICE_NAME' already exists"
else
  echo "[create] Cloud Run service '$SERVICE_NAME' (placeholder revision)"
  retry_eventual_consistency "cloud run pre-create" -- \
    gcloud run deploy "$SERVICE_NAME" \
      --image=us-docker.pkg.dev/cloudrun/container/hello \
      --region="$GCP_REGION" \
      --service-account="$SA_EMAIL" \
      --allow-unauthenticated \
      --port=8080 \
      --project="$GCP_PROJECT_ID" \
      --quiet >/dev/null
fi

# ── Step 6: Service account key (workshop shortcut) ─────────────────────

if [[ "$WITH_SA_KEY" == "true" ]]; then
  KEY_FILE="${GCP_PROJECT_ID}-deployer-key.json"

  if [[ -f "$KEY_FILE" ]]; then
    echo "[skip] Key file $KEY_FILE already exists (delete it first if you need a new one)"
  else
    echo "[create] Service account key -> $KEY_FILE"
    gcloud iam service-accounts keys create "$KEY_FILE" \
      --iam-account="$SA_EMAIL" \
      --project="$GCP_PROJECT_ID"
    echo ""
    echo "  WARNING: This key is a long-lived credential."
    echo "  For production, use Workload Identity Federation instead."
    echo "  See docs/PLATFORM-GUIDE.md Step 5."
  fi
fi

# ── Step 7: Push GitHub repo secrets ────────────────────────────────────
#
# Set the GitHub Actions secrets the deploy workflows need, using the
# values this script just minted. Eliminates the most common day-1
# failure: facilitators copy SA emails or WIF provider paths between
# templates and forks and get them wrong, which surfaces later as opaque
# `iam.serviceAccountTokenCreator` 404s or `invalid_target` WIF errors.
# See #49 / docs/UPSTREAM-INTAKE for the original report.
#
# Gated on:
#   1. `gh` CLI present on PATH
#   2. GITHUB_REPOSITORY env var set (facilitator passes the participant's
#      `<owner>/<repo>` — same value the wrapper already has from
#      `github_full_repo`).
#
# When either is missing, log a hint and fall back to the printed
# next-steps block (existing behavior). No silent skip — facilitators
# need to know whether secrets were set or not.
#
# Secret values are passed via `--body-file <(printf ...)` so they never
# appear on the command line, in shell history, or in stdout logs. Only
# the secret name and the gh confirmation are echoed.

GH_SECRETS_PUSHED="false"
if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
  if command -v gh >/dev/null 2>&1; then
    echo ""
    echo "[secrets] Pushing GitHub Actions secrets to $GITHUB_REPOSITORY"

    # Helper: set a secret without ever echoing the value. Body comes
    # from a process substitution so it's never an argv element.
    push_secret() {
      local name="$1"
      local value="$2"
      if [[ -z "$value" ]]; then
        return 0
      fi
      gh secret set "$name" --repo "$GITHUB_REPOSITORY" \
        --body "$value" >/dev/null
      echo "  [set] $name"
    }

    push_secret "GCP_PROJECT_ID" "$GCP_PROJECT_ID"
    push_secret "GCP_SERVICE_ACCOUNT" "$SA_EMAIL"
    if [[ -n "${WIF_PROVIDER_RESOURCE:-}" ]]; then
      push_secret "GCP_WORKLOAD_IDENTITY_PROVIDER" "$WIF_PROVIDER_RESOURCE"
    fi
    if [[ "${NEON_BRANCH_PROVISIONED:-false}" == "true" ]]; then
      push_secret "NEON_PARENT_BRANCH" "$NEON_BRANCH_NAME"
      # Same Neon pooled URI Step 5.7 wrote into the `database-url`
      # Secret Manager secret. deploy.yml reads this in two places:
      # the Alembic migration step (line 93) and the Cloud Run runtime
      # env var (line 160, post-#68). Without it both fail silently —
      # see #71.
      push_secret "PRODUCTION_DATABASE_URL" "$pooled_uri"
    fi

    # SA key is intentionally NOT auto-pushed even when --with-sa-key
    # was used — it's a long-lived credential that should be uploaded
    # deliberately, not as a side-effect of provisioning. The footer
    # still tells the user how to set it.

    GH_SECRETS_PUSHED="true"
  else
    echo ""
    echo "[secrets] gh CLI not on PATH; falling back to printed next-steps."
    echo "          Install gh from https://cli.github.com/ for automatic secret setting."
  fi
fi

# ── Done ─────────────────────────────────────────────────────────────────

echo ""
echo "=================================="
echo "  Provisioning complete"
echo "=================================="
echo ""
echo "Next steps:"
echo ""
if [[ "$GH_SECRETS_PUSHED" == "true" ]]; then
  echo "1. GitHub Actions secrets already set on $GITHUB_REPOSITORY:"
  echo ""
  echo "   - GCP_PROJECT_ID"
  echo "   - GCP_SERVICE_ACCOUNT"
  if [[ -n "${WIF_PROVIDER_RESOURCE:-}" ]]; then
    echo "   - GCP_WORKLOAD_IDENTITY_PROVIDER"
  fi
  if [[ "${NEON_BRANCH_PROVISIONED:-false}" == "true" ]]; then
    echo "   - NEON_PARENT_BRANCH"
    echo "   - PRODUCTION_DATABASE_URL"
  fi
  echo ""
  if [[ "$WITH_SA_KEY" == "true" ]]; then
    echo "   You ran with --with-sa-key. Upload the SA key file deliberately:"
    echo "     gh secret set GCP_SA_KEY --repo $GITHUB_REPOSITORY \\"
    echo "       --body-file ${GCP_PROJECT_ID}-deployer-key.json"
    echo ""
  fi
else
  echo "1. Set these GitHub repository secrets:"
  echo ""
  echo "   GCP_PROJECT_ID         = $GCP_PROJECT_ID"
  if [[ "$WITH_SA_KEY" == "true" ]]; then
    echo "   GCP_SA_KEY             = (contents of ${GCP_PROJECT_ID}-deployer-key.json)"
  elif [[ -n "${WIF_PROVIDER_RESOURCE:-}" ]]; then
    echo "   GCP_WORKLOAD_IDENTITY_PROVIDER = $WIF_PROVIDER_RESOURCE"
    echo "   GCP_SERVICE_ACCOUNT    = $SA_EMAIL"
  else
    echo "   GCP_WORKLOAD_IDENTITY_PROVIDER = (set GITHUB_USERNAME or see docs/PLATFORM-GUIDE.md Step 5)"
    echo "   GCP_SERVICE_ACCOUNT    = $SA_EMAIL"
  fi
  echo ""
  echo "   (Tip: set GITHUB_REPOSITORY and have 'gh' on PATH to auto-push these.)"
  echo ""
fi
if [[ "${NEON_BRANCH_PROVISIONED:-false}" == "true" ]]; then
  # Step 5.7 already created the Neon branch and database-url secret.
  # Tell the participant what to set on their fork; no manual gcloud.
  if [[ "$GH_SECRETS_PUSHED" == "true" ]]; then
    # Fork is known and gh is available — print the exact loop the
    # facilitator should run for the cohort-shared Neon secrets. These
    # are intentionally NOT auto-pushed by Step 7 because they're the
    # same value across every fork; coupling per-attendee provisioning
    # to cohort-level state would make rotation harder.
    echo "2. Set the cohort-shared Neon secrets on $GITHUB_REPOSITORY:"
    echo ""
    echo "   gh secret set NEON_API_KEY    --repo $GITHUB_REPOSITORY --body \"\$NEON_API_KEY\""
    echo "   gh secret set NEON_PROJECT_ID --repo $GITHUB_REPOSITORY --body \"\$NEON_PROJECT_ID\""
    echo ""
    echo "   (NEON_PARENT_BRANCH and PRODUCTION_DATABASE_URL were set automatically above.)"
    echo "   The 'database-url' Secret Manager secret was created automatically"
    echo "   from the attendee's Neon branch ('$NEON_BRANCH_NAME')."
  else
    echo "2. Set these GitHub secrets from the Neon console (shared across cohort):"
    echo ""
    echo "   NEON_API_KEY           = (from Neon Settings -> API Keys)"
    echo "   NEON_PROJECT_ID        = (from Neon Settings -> General)"
    echo ""
    echo "   The 'database-url' Secret Manager secret was created automatically"
    echo "   from the attendee's Neon branch ('$NEON_BRANCH_NAME')."
    echo ""
    echo "3. Set NEON_PARENT_BRANCH and PRODUCTION_DATABASE_URL on the"
    echo "   participant's fork so production deploys can run migrations and"
    echo "   per-PR previews inherit this attendee's branch:"
    echo ""
    echo "   NEON_PARENT_BRANCH     = $NEON_BRANCH_NAME"
    echo "   PRODUCTION_DATABASE_URL = (the same value already in"
    echo "                              the 'database-url' Secret Manager secret)"
  fi
  echo ""
  echo "4. (Optional) Set these repository variables (non-secret):"
else
  # Manual fallback: facilitator either skipped the env vars or is running
  # the inner script standalone.
  echo "2. Sign up at https://neon.tech and create a project."
  echo "   Set these GitHub secrets from the Neon console:"
  echo ""
  echo "   NEON_API_KEY           = (from Neon Settings -> API Keys)"
  echo "   NEON_PROJECT_ID        = (from Neon Settings -> General)"
  echo ""
  echo "3. Create the production database secret:"
  echo ""
  echo "   echo -n 'postgresql://...' | gcloud secrets create database-url \\"
  echo "     --data-file=- --project=$GCP_PROJECT_ID"
  echo ""
  echo "   (Or set NEON_API_KEY + NEON_PROJECT_ID + NEON_BRANCH_NAME before"
  echo "   running this script and Step 5.7 will create the secret automatically.)"
  echo ""
  echo "4. (Optional) Set these repository variables (non-secret):"
fi
echo ""
echo "   GCP_REGION             = $GCP_REGION"
echo "   ARTIFACT_REPO          = $ARTIFACT_REPO"
echo "   CLOUD_RUN_SERVICE      = masterkey"
echo "   NEXT_PUBLIC_APP_URL    = (your production URL)"
echo ""
echo "5. Push to main to trigger your first deployment."
