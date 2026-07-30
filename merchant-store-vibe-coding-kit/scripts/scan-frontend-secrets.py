#!/usr/bin/env python3
"""Fail when server-side credential names or likely live secrets enter the UI tree."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FORBIDDEN_NAMES = {
    "PINGBIZ_MERCHANT_IDENTIFIER",
    "PINGBIZ_STORE_IDENTIFIER",
    "PINGBIZ_MERCHANT_API_KEY",
    "ESTORE_CLIENT_SECRET",
    "KC_BOOTSTRAP_ADMIN_PASSWORD",
    "KC_DB_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "BIZ_APP_BASE_URL",
}
ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|client[_-]?secret|password|bearer|authorization)\s*[:=]\s*['\"]([A-Za-z0-9_./+=-]{24,})['\"]"
)
TEXT_SUFFIXES = {
    ".ts", ".js", ".mjs", ".cjs", ".json", ".html", ".css", ".scss",
    ".md", ".txt", ".map", ".xml", ".yaml", ".yml", ".env"
}
SKIP_DIRS = {"node_modules", ".git", ".angular", ".cache"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    findings: list[str] = []
    for root in args.paths:
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "docker-entrypoint.sh"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for name in sorted(FORBIDDEN_NAMES):
                if name in text:
                    findings.append(f"{path}: contains forbidden server credential name {name}")
            for match in ASSIGNMENT.finditer(text):
                value = match.group(1)
                if not value.startswith(("REPLACE_", "GENERATE_", "${", "__")):
                    findings.append(f"{path}: contains a likely embedded secret assignment")
    if findings:
        print("FAIL: frontend secret scan", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("PASS: frontend contains no server credential names or likely embedded secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
