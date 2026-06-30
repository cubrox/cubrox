#!/usr/bin/env bash
# Validates the version field in .gembaflow-version against package.json.
#
# Default mode (lenient): warns if versions diverge, does not fail.
# Opt-in mode (strict):   fails if versions diverge.
#
# Forks that ship a product on its own version cadence will see framework
# version (`.gembaflow-version`) and app version (`package.json`) diverge as
# a normal lifecycle event. Strict parity is the right policy only for
# distributions where the two MUST move together (e.g. a fork that vendors
# the framework into its own package and re-publishes it).
#
# To opt back into strict mode, add to your fork's `.gembaflow-version`:
#
#   "enforceVersionParity": true
#
# See `docs/UPGRADING.md` § "Version parity policy" for the full rationale.

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
ENFORCE=$(jq -r '.enforceVersionParity // false' "$MANIFEST")

if [ -z "$MANIFEST_VERSION" ]; then
  echo "FAIL: $MANIFEST has no version field"
  exit 1
fi

if [ -z "$PACKAGE_VERSION" ]; then
  echo "FAIL: $PACKAGE has no version field"
  exit 1
fi

if [ "$MANIFEST_VERSION" = "$PACKAGE_VERSION" ]; then
  echo "PASS: Version $MANIFEST_VERSION matches across $MANIFEST and $PACKAGE"
  exit 0
fi

# Versions diverge — strict vs lenient decides exit code.
if [ "$ENFORCE" = "true" ]; then
  echo "FAIL: Version mismatch (strict mode — enforceVersionParity=true)"
  echo "  $MANIFEST: $MANIFEST_VERSION"
  echo "  $PACKAGE:  $PACKAGE_VERSION"
  echo ""
  echo "Update both files to the same version, or set"
  echo "  \"enforceVersionParity\": false  (the default)"
  echo "in $MANIFEST if your fork ships on a separate version cadence."
  exit 1
fi

echo "WARN: Version diverges between $MANIFEST and $PACKAGE — check skipped in lenient mode."
echo "  $MANIFEST: $MANIFEST_VERSION"
echo "  $PACKAGE:  $PACKAGE_VERSION"
echo ""
echo "If your fork requires strict parity, set"
echo "  \"enforceVersionParity\": true"
echo "in $MANIFEST."
exit 0
