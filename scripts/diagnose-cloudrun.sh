#!/bin/bash
#
# diagnose-cloudrun.sh — One-shot Cloud Run diagnostic snapshot
#
# Read-only. Prints a structured summary of a Cloud Run service so a
# facilitator can paste the output into a help channel and someone
# else can diagnose without a back-and-forth.
#
# Sections (in order):
#   1. Service summary (URL, latest-ready vs latest-created revision)
#   2. Traffic split (which revisions get how much traffic)
#   3. Currently-serving image (placeholder-image trap surfaces here)
#   4. Latest revision conditions (Ready, Active, ContainerHealthy)
#   5. Last 50 log lines from the service
#
# Usage:
#   ./scripts/diagnose-cloudrun.sh                       # uses GCP_PROJECT_ID env
#   ./scripts/diagnose-cloudrun.sh --project=af-xxx      # explicit project
#   ./scripts/diagnose-cloudrun.sh --project=af-xxx --service=my-svc --region=us-central1
#   ./scripts/diagnose-cloudrun.sh --help
#
# Required: GCP_PROJECT_ID env or --project=<id>
# Optional: GCP_REGION (default: us-central1), CLOUD_RUN_SERVICE (default: masterkey)
#
# Surfaced from the 2026-04-29 dry-run on tck517/tck517-app, where the
# diagnostic command that cracked the case was a hand-composed multi-
# field gcloud query. See #64.

set -uo pipefail

# ── Argument parsing ────────────────────────────────────────────────────

PROJECT="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE:-masterkey}"

print_help() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      print_help
      exit 0
      ;;
    --project=*)
      PROJECT="${1#*=}"
      ;;
    --service=*)
      SERVICE="${1#*=}"
      ;;
    --region=*)
      REGION="${1#*=}"
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Run '$0 --help' for usage." >&2
      exit 2
      ;;
  esac
  shift
done

# ── Pre-flight ──────────────────────────────────────────────────────────

if [[ -z "$PROJECT" ]]; then
  echo "ERROR: project is required." >&2
  echo "  Set GCP_PROJECT_ID env or pass --project=<id>." >&2
  echo "  (Refusing to fall back to 'gcloud config get project' to avoid" >&2
  echo "   silently diagnosing the wrong project.)" >&2
  exit 2
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud CLI is not on PATH." >&2
  echo "  Install: https://cloud.google.com/sdk/docs/install" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not on PATH (needed for JSON parsing)." >&2
  exit 2
fi

# ── Fetch service JSON (single round-trip) ──────────────────────────────

SERVICE_JSON_FILE="$(mktemp -t diagnose-cloudrun-XXXXXX)"
trap 'rm -f "$SERVICE_JSON_FILE" "${REV_JSON_FILE:-}"' EXIT

if ! gcloud run services describe "$SERVICE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --format=json > "$SERVICE_JSON_FILE" 2>"$SERVICE_JSON_FILE.err"; then
  echo "ERROR: could not describe service '$SERVICE' in $PROJECT/$REGION" >&2
  cat "$SERVICE_JSON_FILE.err" >&2
  rm -f "$SERVICE_JSON_FILE.err"
  exit 1
fi
rm -f "$SERVICE_JSON_FILE.err"

# Helper: run a python heredoc with the service JSON path as argv[1].
parse_service_json() {
  python3 - "$SERVICE_JSON_FILE"
}

# ── Section 1: Service summary ──────────────────────────────────────────

echo "=== Cloud Run service: $SERVICE ==="

parse_service_json <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
status = data.get("status", {})
metadata = data.get("metadata", {})
url = status.get("url", "(none)")
latest_ready = status.get("latestReadyRevisionName", "(none)")
latest_created = status.get("latestCreatedRevisionName", "(none)")
namespace = metadata.get("namespace", "(unknown)")
location = metadata.get("labels", {}).get("cloud.googleapis.com/location", "(unknown)")
print(f"Project:              {namespace}")
print(f"Region:               {location}")
print(f"URL:                  {url}")
print(f"Latest READY:         {latest_ready}")
print(f"Latest CREATED:       {latest_created}")
if latest_ready != latest_created:
    print(f"  WARN latest-created differs from latest-ready — newest revision is not yet ready")
PY

# ── Section 2: Traffic split ────────────────────────────────────────────

echo ""
echo "=== Traffic split ==="

parse_service_json <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
status = data.get("status", {})
latest_ready = status.get("latestReadyRevisionName", "")
traffic = status.get("traffic", [])
if not traffic:
    print("(no traffic entries returned)")
else:
    for entry in traffic:
        pct = entry.get("percent", 0)
        rev = entry.get("revisionName") or entry.get("latestRevision", "(latest)")
        if entry.get("latestRevision"):
            rev = f"{rev} (= latestRevision flag)"
        marker = ""
        if latest_ready and entry.get("revisionName") and entry.get("revisionName") != latest_ready:
            marker = f"   <- STALE (latest-ready is {latest_ready})"
        print(f"{pct:>3}% -> {rev}{marker}")
PY

# ── Section 3: Currently-serving image ──────────────────────────────────

echo ""
echo "=== Currently-serving image ==="

parse_service_json <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
spec = data.get("spec", {}).get("template", {}).get("spec", {})
containers = spec.get("containers", [])
if not containers:
    print("(no containers in template spec)")
else:
    for i, c in enumerate(containers):
        image = c.get("image", "(unknown)")
        marker = ""
        if "cloudrun/container/hello" in image:
            marker = "   <- PLACEHOLDER (Step 5.8 pre-create not yet replaced)"
        prefix = "Image:                " if i == 0 else f"Image[{i}]:             "
        print(f"{prefix}{image}{marker}")
PY

# ── Section 4: Latest revision conditions ───────────────────────────────

echo ""
echo "=== Latest revision conditions ==="

LATEST_READY="$(parse_service_json <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
print(data.get("status", {}).get("latestReadyRevisionName", ""))
PY
)"

if [[ -n "$LATEST_READY" ]]; then
  echo "$LATEST_READY:"
  REV_JSON_FILE="$(mktemp -t diagnose-cloudrun-rev-XXXXXX)"
  if gcloud run revisions describe "$LATEST_READY" \
    --region="$REGION" \
    --project="$PROJECT" \
    --format=json > "$REV_JSON_FILE" 2>"$REV_JSON_FILE.err"; then
    python3 - "$REV_JSON_FILE" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
conditions = data.get("status", {}).get("conditions", [])
if not conditions:
    print("  (no conditions reported)")
else:
    for c in conditions:
        ctype = c.get("type", "?")
        cstatus = c.get("status", "?")
        cmsg = c.get("message", "")
        line = f"  {ctype}: {cstatus}"
        if cmsg:
            line += f"  ({cmsg})"
        print(line)
PY
  else
    echo "  (could not describe revision: $(cat "$REV_JSON_FILE.err"))"
  fi
  rm -f "$REV_JSON_FILE.err"
else
  echo "(no latest-ready revision)"
fi

# ── Section 5: Last 50 log lines ────────────────────────────────────────

echo ""
echo "=== Last 50 log lines ==="

# `gcloud logging read --order=desc` gives newest-first; reverse with awk
# (portable across macOS/Linux — `tac` is GNU-only, `tail -r` is BSD-only).
if ! gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE" \
  --project="$PROJECT" \
  --limit=50 \
  --order=desc \
  --format='value(timestamp,severity,textPayload)' 2>/dev/null \
  | awk '{ a[NR] = $0 } END { for (i = NR; i >= 1; i--) print a[i] }'; then
  echo "(could not read logs)"
fi

echo ""
echo "=== End of diagnostic ==="
