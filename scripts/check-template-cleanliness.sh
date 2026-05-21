#!/usr/bin/env bash
# Fails if GCP/AWS/enterprise-specific terms are found in core agile-flow files.
# Self-excluded from the scan to avoid false positives on the pattern strings.
set -euo pipefail

SELF="$(basename "$0")"
FORBIDDEN='\bgcp\b|google-cloud|\bgcloud\b|cloud-run|\baws\b|\bamazon\b|\bec2\b|\bs3\b|\blambda\b'

SCAN_DIRS=(scripts .claude/commands .github/workflows)
SCAN_INCLUDE=(--include='*.sh' --include='*.md' --include='*.yml')

violations=0
for dir in "${SCAN_DIRS[@]}"; do
  [ -d "$dir" ] || continue
  while IFS= read -r match; do
    echo "VIOLATION: $match"
    violations=$((violations + 1))
  done < <(grep -rinP "$FORBIDDEN" "${SCAN_INCLUDE[@]}" --exclude="$SELF" "$dir" 2>/dev/null || true)
done

if [ "$violations" -gt 0 ]; then
  echo ""
  echo "Template cleanliness check FAILED ($violations violation(s))."
  echo "Forbidden terms: gcp, google-cloud, gcloud, cloud-run, aws, amazon, ec2, s3, lambda"
  exit 1
fi

echo "Template cleanliness check PASSED."
