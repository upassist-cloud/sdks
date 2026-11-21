"""Build openapi/public-v1.yaml from the running service definitions.

Management paths come from the public Litestar controllers.
Heartbeat ping and log ingest come from their FastAPI routers.
Do not edit the YAML by hand.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PYTHON = ROOT / "api" / ".venv" / "bin" / "python"
OUT = ROOT / "openapi" / "public-v1.yaml"

MANAGEMENT = "https://api.upassist.cloud"
HEARTBEATS = "https://heartbeats.upassist.cloud"
LOGS = "https://logs.upassist.cloud"
METRICS = "https://metrics.upassist.cloud"
RUM = "https://rum.upassist.cloud"

ERROR_SCHEMA = {
    "type": "object",
    "required": ["code", "message"],
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "request_id": {"type": "string", "nullable": True},
    },
}
ERROR_RESPONSE = {
    "description": "Error",
    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
}


def _run(args: list[str], env: dict[str, str]) -> dict:
    completed = subprocess.run(args, check=True, capture_output=True, text=True, env=env)
    return json.loads(completed.stdout)


def _management_spec() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "api" / "src")
    env["ENV_FILE"] = str(ROOT / "api" / ".env")
    return _run(
        [str(API_PYTHON), "-c", "import json, sys; from domain.public_api.schema_app import public_openapi_dict; json.dump(public_openapi_dict(), sys.stdout)"],
        env,
    )


def _fastapi_spec(service: str, import_line: str = "import routes\nrouter = routes.router") -> dict:
    src = ROOT / service / "src"
    site = ROOT / service / ".venv" / "lib" / "python3.12" / "site-packages"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{src}:{site}"
    code = f"""
import json
import sys
from fastapi import FastAPI
{import_line}

def operation_id(route):
    method = sorted(route.methods)[0].lower()
    return f"{{route.name}}_{{method}}"

app = FastAPI(generate_unique_id_function=operation_id)
app.include_router(router)
json.dump(app.openapi(), sys.stdout)
"""
    return _run([str(API_PYTHON), "-c", code], env)


def _dedupe_operation_ids(spec: dict) -> None:
    counts: dict[str, int] = {}
    for item in (spec.get("paths") or {}).values():
        for operation in item.values():
            if isinstance(operation, dict) and operation.get("operationId"):
                counts[operation["operationId"]] = counts.get(operation["operationId"], 0) + 1
    for item in (spec.get("paths") or {}).values():
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id and counts.get(operation_id, 0) > 1:
                stem = operation_id.rsplit("_", 1)[0]
                operation["operationId"] = f"{stem}_{method}"


def _drop_internal_parameters(spec: dict) -> None:
    hidden = {"db_session"}
    for item in (spec.get("paths") or {}).values():
        for operation in item.values():
            if not isinstance(operation, dict) or "parameters" not in operation:
                continue
            operation["parameters"] = [
                parameter
                for parameter in operation["parameters"]
                if not (
                    parameter.get("name") in hidden
                    or (
                        parameter.get("name") == "Authorization"
                        and parameter.get("in") == "header"
                    )
                )
            ]
            if not operation["parameters"]:
                operation.pop("parameters")


def _strip_schema_ui(spec: dict) -> None:
    paths = spec.get("paths") or {}
    for path in list(paths):
        if path.startswith("/schema"):
            del paths[path]


def _annotate_management(spec: dict) -> None:
    components = spec.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas["Error"] = ERROR_SCHEMA
    for path, item in (spec.get("paths") or {}).items():
        if not path.startswith("/v1/"):
            continue
        for method, operation in item.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            for status in ("400", "401", "403", "404", "422"):
                responses[status] = ERROR_RESPONSE
            operation.setdefault("security", [{"projectApiKey": []}])


def _fix_schema(node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _fix_schema(item)
        return
    if not isinstance(node, dict):
        return
    types = node.get("type")
    if isinstance(types, list) and "additionalProperties" in node:
        branches = []
        for kind in types:
            if kind == "object":
                branches.append({"type": "object", "additionalProperties": True})
            elif kind == "array":
                branches.append({"type": "array", "items": {}})
            else:
                branches.append({"type": kind})
        node.clear()
        node["anyOf"] = branches
    elif node.get("type") == "array" and "items" not in node:
        node["items"] = {}
    if node.get("format") == "duration":
        node["type"] = "string"
        node.pop("format")
    for value in node.values():
        _fix_schema(value)


def _align_titles(spec: dict) -> None:
    for name, schema in ((spec.get("components") or {}).get("schemas") or {}).items():
        if isinstance(schema, dict):
            schema["title"] = name


def _prefix_components(spec: dict, prefix: str) -> None:
    components = spec.get("components") or {}
    renamed: dict[str, dict] = {}
    for section, values in components.items():
        if not isinstance(values, dict):
            renamed[section] = values
            continue
        renamed[section] = {f"{prefix}{name}": value for name, value in values.items()}
    spec["components"] = renamed
    raw = json.dumps(spec)
    for section, values in components.items():
        if not isinstance(values, dict):
            continue
        for name in values:
            raw = raw.replace(f"#/components/{section}/{name}", f"#/components/{section}/{prefix}{name}")
    spec.clear()
    spec.update(json.loads(raw))


def _retarget(spec: dict, server: str) -> None:
    for item in (spec.get("paths") or {}).values():
        for operation in item.values():
            if isinstance(operation, dict):
                operation["servers"] = [{"url": server}]
                operation.pop("security", None)


def merge() -> dict:
    management = _management_spec()
    _strip_schema_ui(management)
    _annotate_management(management)

    heartbeats = _fastapi_spec("heartbeats_ping_api")
    logs = _fastapi_spec("logs_api")
    metrics = _fastapi_spec("metrics_api")
    rum = _fastapi_spec("rum_api", "from routers.events import router")
    _prefix_components(heartbeats, "Heartbeat")
    _prefix_components(logs, "Logs")
    _prefix_components(metrics, "Metrics")
    _prefix_components(rum, "Rum")
    _retarget(heartbeats, HEARTBEATS)
    _retarget(logs, LOGS)
    _retarget(metrics, METRICS)
    _retarget(rum, RUM)

    for source in (heartbeats, logs, rum):
        for path, item in (source.get("paths") or {}).items():
            if path == "/health":
                continue
            management["paths"][path] = item
        for section, values in (source.get("components") or {}).items():
            if isinstance(values, dict):
                management.setdefault("components", {}).setdefault(section, {}).update(values)
    for section, values in (metrics.get("components") or {}).items():
        if isinstance(values, dict):
            management.setdefault("components", {}).setdefault(section, {}).update(values)

    management["servers"] = [
        {"url": MANAGEMENT, "description": "Management"},
        {"url": HEARTBEATS, "description": "Heartbeat ingest"},
        {"url": LOGS, "description": "Log ingest"},
        {"url": METRICS, "description": "Metric ingest"},
        {"url": RUM, "description": "Site events"},
    ]
    _drop_internal_parameters(management)
    _dedupe_operation_ids(management)
    _fix_schema(management)
    _align_titles(management)
    schemes = management.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["sourceToken"] = {
        "type": "http",
        "scheme": "bearer",
        "description": "Log source secret token",
    }
    for path, item in management["paths"].items():
        security = None
        if path.startswith("/api/event") or path.startswith("/api/ping"):
            security = [{"projectApiKey": []}]
        elif path == "/collect":
            security = [{"sourceToken": []}]
        elif path.startswith("/api/sites/events"):
            security = []
        if security is None:
            continue
        for operation in item.values():
            if isinstance(operation, dict):
                operation["security"] = security

    info = management.setdefault("info", {})
    info["description"] = (
        (info.get("description") or "").rstrip()
        + "\n\nHeartbeat pings go to the heartbeat server. "
        + "Log batches go to https://logs.upassist.cloud/collect and use a source token. "
        + "Metric batches go to https://metrics.upassist.cloud/collect with the same source token. "
        + "Site events go to https://rum.upassist.cloud/api/sites/events with the site client key. "
        + "Application errors use the official Sentry SDKs."
    )
    return management


def _assert_contract(spec: dict) -> None:
    servers = [server["url"] for server in spec["servers"]]
    if "https://api.upassist.cloud" not in servers or any(url.endswith("/v1") for url in servers):
        raise SystemExit(f"unexpected servers: {servers}")
    seen: set[str] = set()
    for path, item in spec["paths"].items():
        if path.startswith("/schema") or path == "/health":
            raise SystemExit(f"internal path leaked: {path}")
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not operation_id or operation_id in seen:
                raise SystemExit(f"bad operationId {operation_id} on {method} {path}")
            seen.add(operation_id)
            for parameter in operation.get("parameters") or []:
                if parameter.get("name") in {"db_session", "Authorization"}:
                    raise SystemExit(f"internal parameter on {method} {path}")


def main() -> None:
    import yaml

    spec = merge()
    _assert_contract(spec)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {OUT} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "api" / "src"))
    main()
