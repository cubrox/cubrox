#!/usr/bin/env bash
# Validates that .gembaflow-version and package.json agree on the version
# field. Runs in CI to prevent version drift between the two files.

set -euo pipefail

MANIFEST=".gembaflow-version"
PACKAGE="package.json"

if [ ! -f "$MANIFEST" ]; then
  echo "SKIP: $MANIFEST not found (not yet bootstrapped)"
  exit 0
fi

if [ ! -f "$PACKAGE" ]; then
  echo "SKIP: $PACKAGE not found (non-Node project)"
  exit 0
fi

MANIFEST_VERSION=$(jq -r '.version // empty' "$MANIFEST")
PACKAGE_VERSION=$(jq -r '.version // empty' "$PACKAGE")

if [ -z "$MANIFEST_VERSION" ]; then
  echo "FAIL: $MANIFEST has no version field"
  exit 1
fi

if [ -z "$PACKAGE_VERSION" ]; then
  echo "FAIL: $PACKAGE has no version field"
  exit 1
fi

if [ "$MANIFEST_VERSION" != "$PACKAGE_VERSION" ]; then
  echo "FAIL: Version mismatch"
  echo "  $MANIFEST: $MANIFEST_VERSION"
  echo "  $PACKAGE:  $PACKAGE_VERSION"
  echo ""
  echo "Update both files to the same version before merging."
  exit 1
fi

echo "PASS: Version $MANIFEST_VERSION matches across $MANIFEST and $PACKAGE"
