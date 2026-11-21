# Upassist SDKs & Code Generation Toolchain

Official multi-language SDK monorepo, code generation pipeline, and OpenAPI 3.1 specifications for the [Upassist](https://upassist.cloud) platform.

## Repository Overview

This repository coordinates the generation, packaging, and distribution of official Upassist client libraries:

| Language | Package | Repository | Description |
|---|---|---|---|
| **Python** | `upassist` | [upassist-cloud/upassist-python](https://github.com/upassist-cloud/upassist-python) | Sync (`Upassist`) & Async (`AsyncUpassist`) clients + `upassist` CLI |
| **TypeScript / JS** | `upassist` | [upassist-cloud/upassist-js](https://github.com/upassist-cloud/upassist-js) | Dual ESM/CJS build with full TypeScript definitions |
| **Go** | `upassist-go` | [upassist-cloud/upassist-go](https://github.com/upassist-cloud/upassist-go) | Typed client + high-performance compiled `upassist` CLI |

---

## Directory Structure

```text
sdks/
├── openapi/
│   └── public-v1.yaml         # Complete, canonical OpenAPI 3.1 schema for Upassist
├── scripts/
│   ├── export_public_openapi.py # Exports & merges Litestar + FastAPI public endpoints
│   ├── generate_sdks.sh       # Master generation script for Python, TypeScript, and Go
│   └── publish_release.sh     # Tags and triggers multi-repository releases
├── facade/                    # High-level ergonomic wrappers, facades, and CLI tools
│   ├── sdk.py                 # Synchronous and Asynchronous resource facades
│   ├── cli.py                 # Official `upassist` command-line interface
│   └── README.md              # Gold-standard documentation template for Python
├── python-client.yaml         # openapi-python-client generator configuration
├── typescript-generator/      # @hey-api/openapi-ts generator dependencies
├── python/                    # Python package source (submodule: upassist-cloud/upassist-python)
├── typescript/                # TypeScript package source (submodule: upassist-cloud/upassist-js)
└── go/                        # Go module source (submodule: upassist-cloud/upassist-go)
```

---

## Prerequisites

To run the SDK generation pipeline locally or in CI:

- **Python 3.11+** with `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 20+** with `npm`
- **Go 1.22+**
- Toolchain binaries (`openapi-python-client`, `@hey-api/openapi-ts`, `oapi-codegen`) are installed automatically into `.tools/` by `scripts/generate_sdks.sh`.

---

## Generating SDKs

Whenever API endpoints or schemas change in `api/`:

```bash
# 1. Regenerate OpenAPI schema and all three SDK clients:
bash scripts/generate_sdks.sh
```

The script will:
1. Export clean OpenAPI 3.1 YAML from the running backend service definitions.
2. Filter internal and ingest paths, standardizing on `/v1` management operations.
3. Generate the Python client, inject ergonomic facades (`sdk.py`), wire up the CLI, and build distribution wheels.
4. Generate the TypeScript client, compile dual ESM/CJS bundles, and emit `.d.ts` declaration maps.
5. Generate the Go client via `oapi-codegen` and compile the Go CLI binary.

---

## Releasing a New Version

To publish a synchronized release across all SDKs:

```bash
# Example: release version 1.0.0
bash scripts/publish_release.sh 1.0.0
```

This will automatically create and push Git tags (`v1.0.0`) to:
- `upassist-cloud/upassist-python` (triggers PyPI release via GitHub Actions)
- `upassist-cloud/upassist-js` (triggers npm release via GitHub Actions)
- `upassist-cloud/upassist-go` (triggers Go Releaser via GitHub Actions)

---

## License

MIT
