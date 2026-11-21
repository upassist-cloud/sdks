#!/usr/bin/env bash
# Quick release script for Upassist SDKs & API
set -euo pipefail

VERSION="${1:-1.0.0}"
TAG="v$VERSION"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=================================================="
echo " Preparing Upassist Release $TAG"
echo "=================================================="

# 1. Regenerate all clients from current API schema
echo "[1/4] Regenerating clients from OpenAPI schema..."
bash "$ROOT/scripts/generate_sdks.sh"

# 2. Tag and push Python SDK
echo "[2/4] Tagging Python SDK ($TAG)..."
cd "$ROOT/sdks/python"
git tag -f "$TAG"
git push origin "$TAG" -f
echo " -> Pushed tag $TAG to github.com/upassist-cloud/upassist-python"

# 3. Tag and push TypeScript SDK
echo "[3/4] Tagging TypeScript SDK ($TAG)..."
cd "$ROOT/sdks/typescript"
git tag -f "$TAG"
git push origin "$TAG" -f
echo " -> Pushed tag $TAG to github.com/upassist-cloud/upassist-js"

# 4. Tag and push Go SDK
echo "[4/4] Tagging Go SDK ($TAG)..."
cd "$ROOT/sdks/go"
git tag -f "$TAG"
git push origin "$TAG" -f
echo " -> Pushed tag $TAG to github.com/upassist-cloud/upassist-go"

echo "=================================================="
echo " All tags ($TAG) successfully pushed to GitHub!"
echo " GitHub Actions workflows have been triggered."
echo "=================================================="
