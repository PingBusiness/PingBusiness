#!/usr/bin/env python3
"""Run non-destructive public checks after DNS and TLS are active."""
from __future__ import annotations

import argparse
import json
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


def fetch(url: str, *, expect_json: bool = False) -> tuple[int, str, object | None, str]:
    req = Request(url, headers={"User-Agent": "PingBusiness-Deployment-SmokeTest/1.0"})
    with urlopen(req, timeout=20, context=ssl.create_default_context()) as response:
        body = response.read(1_000_000).decode("utf-8", errors="replace")
        final_url = response.geturl()
        payload = json.loads(body) if expect_json else None
        return response.status, body, payload, final_url


def same_public_host(expected_host: str, final_url: str) -> None:
    parsed = urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname != expected_host:
        raise RuntimeError(f"unexpected redirect target: {final_url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-url", required=True)
    parser.add_argument("--realm", default="ESTORE")
    args = parser.parse_args()
    base = args.store_url.rstrip("/") + "/"
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname:
        print("FAIL: --store-url must be an HTTPS origin", file=sys.stderr)
        return 2

    checks = [
        ("edge", "edge-health", False),
        ("ui", "healthz", False),
        ("estore-app", "api/health", True),
        ("keycloak-discovery", f"auth/realms/{args.realm}/.well-known/openid-configuration", True),
    ]
    failed = False
    for name, path, expect_json in checks:
        url = urljoin(base, path)
        try:
            status, body, payload, final_url = fetch(url, expect_json=expect_json)
            same_public_host(parsed.hostname, final_url)
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            if name == "edge" and body.strip() != "ok":
                raise RuntimeError(f"unexpected body: {body[:200]!r}")
            if name == "keycloak-discovery":
                issuer = str((payload or {}).get("issuer", ""))
                expected = urljoin(base, f"auth/realms/{args.realm}")
                if issuer.rstrip("/") != expected.rstrip("/"):
                    raise RuntimeError(f"issuer mismatch: {issuer!r}, expected {expected!r}")
            print(f"PASS: {name}: {url}")
        except (HTTPError, URLError, ValueError, RuntimeError) as exc:
            failed = True
            print(f"FAIL: {name}: {url}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
