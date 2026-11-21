#!/usr/bin/env bash
# Rebuild openapi/public-v1.yaml and the generated clients.
# Edit the public controllers, then run this. Do not edit generated files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/api/.venv/bin/python"
SPEC="$(mktemp)"
trap 'rm -f "$SPEC"' EXIT

"$PY" "$ROOT/scripts/export_public_openapi.py"
"$PY" - "$ROOT/openapi/public-v1.yaml" "$SPEC" <<'PY'
import sys
import yaml

source, dest = sys.argv[1:]
spec = yaml.safe_load(open(source, encoding="utf-8"))
spec["paths"] = {
    path: item for path, item in spec["paths"].items() if path.startswith("/v1/")
}
spec["servers"] = [{"url": "https://api.upassist.cloud", "description": "Management"}]
with open(dest, "w", encoding="utf-8") as handle:
    yaml.safe_dump(spec, handle, sort_keys=False, allow_unicode=True)
print(f"management paths: {len(spec['paths'])}")
PY

TOOLS="$ROOT/sdks/.tools"
if [[ ! -x "$TOOLS/py/bin/openapi-python-client" ]]; then
  uv venv "$TOOLS/py"
  uv pip install --python "$TOOLS/py/bin/python" "openapi-python-client==0.29.1"
fi
PATH="$TOOLS/py/bin:$PATH" \
  openapi-python-client generate \
    --path "$SPEC" \
    --config "$ROOT/sdks/python-client.yaml" \
    --meta uv \
    --output-path "$ROOT/sdks/python" \
    --overwrite

if [[ ! -x "$TOOLS/node_modules/.bin/openapi-ts" ]]; then
  mkdir -p "$TOOLS"
  cp "$ROOT/sdks/typescript-generator/package.json" "$TOOLS/package.json"
  npm install --prefix "$TOOLS" --silent
fi
"$TOOLS/node_modules/.bin/openapi-ts" \
  -i "$SPEC" \
  -o "$ROOT/sdks/typescript/src" \
  -c @hey-api/client-fetch
(cd "$ROOT/sdks/typescript" && "$TOOLS/node_modules/.bin/tsup" --config tsup.config.ts --silent)
"$TOOLS/node_modules/.bin/tsc" \
  --project "$ROOT/sdks/typescript/tsconfig.json" \
  --declaration --emitDeclarationOnly --outDir "$ROOT/sdks/typescript/dist"

GO="$(command -v go || true)"
if [[ -z "$GO" && -x /tmp/go/bin/go ]]; then
  GO=/tmp/go/bin/go
fi
if [[ -z "$GO" ]]; then
  echo "go is not installed; skipped the Go client" >&2
  exit 1
fi
export PATH="$(dirname "$GO"):$PATH"
GOBIN="$TOOLS/go/bin"
mkdir -p "$GOBIN"
GOBIN="$GOBIN" GOPATH="${GOPATH:-$TOOLS/go}" GOCACHE="${GOCACHE:-$TOOLS/go/cache}" \
  "$GO" install github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@v2.8.0
PATH="$(dirname "$GO"):$GOBIN:$PATH" "$GOBIN/oapi-codegen" \
  -generate types,client \
  -package upassist \
  -o "$ROOT/sdks/go/client.gen.go" \
  "$SPEC"

if grep -R --include='*.py' --include='*.ts' --include='*.go' -n '/api/event\|/collect' \
  "$ROOT/sdks/python/upassist/api" "$ROOT/sdks/typescript/src" "$ROOT/sdks/go/client.gen.go" >/dev/null; then
  echo "generated management clients still contain ingest paths" >&2
  exit 1
fi

cp "$ROOT/sdks/facade/sdk.py" "$ROOT/sdks/python/upassist/sdk.py"
cp "$ROOT/sdks/facade/cli.py" "$ROOT/sdks/python/upassist/cli.py"
cp "$ROOT/sdks/facade/README.md" "$ROOT/sdks/python/README.md"
cat > "$ROOT/sdks/python/upassist/__init__.py" <<'EOF'
"""Official Python SDK and CLI for the Upassist Monitoring & Observability Platform."""

from .client import AuthenticatedClient, Client
from .sdk import APIError, AsyncUpassist, IngestError, Upassist

__all__ = (
    "APIError",
    "AsyncUpassist",
    "AuthenticatedClient",
    "Client",
    "IngestError",
    "Upassist",
)
EOF

if ! grep -q '\[project.scripts\]' "$ROOT/sdks/python/pyproject.toml"; then
  cat >> "$ROOT/sdks/python/pyproject.toml" <<'EOF'

[project.scripts]
upassist = "upassist.cli:main"
EOF
fi
echo "generated Python (with CLI), TypeScript, and Go clients from /v1"
