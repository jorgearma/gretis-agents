#!/usr/bin/env python3
"""
analyzers/services.py — Genera SERVICES_MAP.json.

Detecta integraciones externas por:
1. Imports de SDKs conocidos (twilio, stripe, boto3, etc.)
2. Patrones de env vars de credenciales (_KEY, _SECRET, _TOKEN, _URL)
3. Archivos en carpetas services/, adapters/, providers/
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from analyzers.core import FileInfo, detect_stack, walk_repo, find_test_file

# SDK → (nombre display, tipo)
SDK_MAP: dict[str, tuple[str, str]] = {
    "twilio":        ("Twilio", "sms"),
    "vonage":        ("Vonage", "sms"),
    "sinch":         ("Sinch", "sms"),
    "sendgrid":      ("SendGrid", "email"),
    "mailgun":       ("Mailgun", "email"),
    "boto3":         ("AWS S3", "storage"),
    "stripe":        ("Stripe", "payments"),
    "monei":         ("Monei", "payments"),
    "paypalrestsdk": ("PayPal", "payments"),
    "braintree":     ("Braintree", "payments"),
    "google.cloud.storage": ("GCS", "storage"),
    "azure.storage": ("Azure Storage", "storage"),
    "redis":         ("Redis", "cache"),
    "aioredis":      ("Redis (async)", "cache"),
    "memcache":      ("Memcached", "cache"),
    "celery":        ("Celery", "queue"),
    "rq":            ("RQ", "queue"),
    "dramatiq":      ("Dramatiq", "queue"),
    "sentry_sdk":    ("Sentry", "monitoring"),
    "datadog":       ("Datadog", "monitoring"),
    "newrelic":      ("New Relic", "monitoring"),
    "httpx":         ("httpx", "other"),
    "requests":      ("requests", "other"),
}

# Display name → (sdk_key, type) for stack-based detection
DISPLAY_TO_SDK: dict[str, tuple[str, str]] = {
    v[0]: (k, v[1]) for k, v in SDK_MAP.items()
}

# Patrones de env vars de credenciales
RE_ENV_VAR = re.compile(
    r'(?:os\.environ\.get|os\.environ|os\.getenv)\s*[\[\(]\s*["\']([A-Z][A-Z0-9_]+(?:_KEY|_SECRET|_TOKEN|_URL|_SID|_API|_PASSWORD|_PASS|_AUTH)["\'])',
)


def _detect_integrations(
    files: list[FileInfo], root: Path, stack: dict
) -> list[dict]:
    integrations: dict[str, dict] = {}

    for fi in files:
        is_service_file = any(
            seg in fi.rel_path.lower()
            for seg in ("service", "adapter", "provider", "integration", "client")
        )

        # Detect by known external imports
        for imp in fi.imports_external:
            imp_lower = imp.lower().replace("-", "_")
            for sdk_key, (sdk_name, sdk_type) in SDK_MAP.items():
                if imp_lower == sdk_key or imp_lower.startswith(sdk_key + "."):
                    if sdk_name not in integrations:
                        integrations[sdk_name] = {
                            "name": sdk_name,
                            "type": sdk_type,
                            "files": [],
                            "functions": [],
                            "env_vars": [],
                        }
                    if fi.rel_path not in integrations[sdk_name]["files"]:
                        integrations[sdk_name]["files"].append(fi.rel_path)
                    integrations[sdk_name]["functions"].extend(
                        [fn for fn in fi.functions if not fn.startswith("_")][:5]
                    )

        # Detect credential env vars from source
        if is_service_file or any(
            imp.lower().replace("-", "_") in SDK_MAP for imp in fi.imports_external
        ):
            try:
                source = (root / fi.rel_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in RE_ENV_VAR.finditer(source):
                env_name = m.group(1).strip("\"'")
                # Assign env var to the most likely integration by prefix
                assigned = False
                for sdk_name, int_data in integrations.items():
                    sdk_prefix = sdk_name.upper().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
                    # 4-char prefix heuristic — pragmatic but imprecise for short prefixes
                    # (e.g. "SEND" matches both SendGrid and custom SEND_* vars).
                    # Env vars are assigned to the first matching integration.
                    if env_name.startswith(sdk_prefix[:4]):
                        if env_name not in int_data["env_vars"]:
                            int_data["env_vars"].append(env_name)
                        assigned = True
                        break
                if not assigned and integrations:
                    # Assign to the integration that already owns this file
                    for sdk_name, int_data in integrations.items():
                        if fi.rel_path in int_data["files"]:
                            if env_name not in int_data["env_vars"]:
                                int_data["env_vars"].append(env_name)
                            break

    # Also detect from requirements.txt stack (display name based)
    for display_name in stack:
        if display_name in DISPLAY_TO_SDK and display_name not in integrations:
            sdk_key, sdk_type = DISPLAY_TO_SDK[display_name]
            integrations[display_name] = {
                "name": display_name,
                "type": sdk_type,
                "files": [],
                "functions": [],
                "env_vars": [],
            }

    # Deduplicate functions
    for int_data in integrations.values():
        int_data["functions"] = list(dict.fromkeys(int_data["functions"]))[:8]

    return list(integrations.values())


def run(root: Path, files: list[FileInfo], stack: dict) -> dict:
    """Genera SERVICES_MAP.json. Escribe en .claude/maps/. Devuelve el dict."""
    integrations = _detect_integrations(files, root, stack)
    for integration in integrations:
        if integration["files"]:
            integration["test_file"] = find_test_file(integration["files"][0], files)
        else:
            integration["test_file"] = None
    result = {"integrations": integrations}

    maps_dir = root / ".claude" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "SERVICES_MAP.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    p = argparse.ArgumentParser(description="Genera SERVICES_MAP.json")
    p.add_argument("--root", default=None)
    args = p.parse_args()
    repo_root = Path(args.root).resolve() if args.root else next(
        (c for c in [Path.cwd(), *Path.cwd().parents] if (c / ".claude").exists()),
        Path.cwd()
    )
    _stack = detect_stack(repo_root)
    _files = walk_repo(repo_root)
    run(repo_root, _files, _stack)
    print("SERVICES_MAP.json generado.")
