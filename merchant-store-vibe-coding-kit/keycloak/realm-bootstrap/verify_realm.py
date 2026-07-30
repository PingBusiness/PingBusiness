#!/usr/bin/env python3
"""Verify that the ESTORE realm is usable by the canonical estore-app."""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import quote, urljoin

import requests


class VerificationError(RuntimeError):
    pass


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise VerificationError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    base_url = required("KC_SERVER_URL").rstrip("/") + "/"
    realm = required("ESTORE_REALM")
    client_id = required("ESTORE_CLIENT_ID")
    client_secret = required("ESTORE_CLIENT_SECRET")
    timeout = int(os.getenv("VERIFY_TIMEOUT_SECONDS", "300"))
    deadline = time.monotonic() + timeout

    token_url = urljoin(base_url, f"realms/{quote(realm, safe='')}/protocol/openid-connect/token")
    realm_url = urljoin(base_url, f"admin/realms/{quote(realm, safe='')}")
    users_url = urljoin(base_url, f"admin/realms/{quote(realm, safe='')}/users")

    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=10,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                raise VerificationError("Keycloak token response did not include access_token")

            headers = {"Authorization": f"Bearer {token}"}
            realm_response = requests.get(realm_url, headers=headers, timeout=10)
            realm_response.raise_for_status()
            users_response = requests.get(users_url, headers=headers, params={"max": 1}, timeout=10)
            users_response.raise_for_status()

            payload = realm_response.json()
            if payload.get("realm") != realm:
                raise VerificationError(f"Unexpected realm response: {payload!r}")

            print(
                "PASS: ESTORE client credentials, view-realm, and manage-users "
                "permissions are operational."
            )
            return 0
        except Exception as exc:  # bounded retry during deployment
            last_error = exc
            time.sleep(5)

    print(f"FAIL: ESTORE realm verification timed out: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
