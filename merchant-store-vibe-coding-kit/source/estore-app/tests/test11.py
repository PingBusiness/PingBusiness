#!/usr/bin/env python3
"""eStore signup requires billing address and phone before Keycloak creation.

Each invalid signup is retried with the same username and valid fields. Success
on retry proves the rejected request did not create a Keycloak login.
"""
from __future__ import annotations

import sys
import uuid
from typing import Any, Dict, Optional

from estore_test_cleanup import cleanup_estore_test_customer
from test1 import EstoreClient, load_config_from_env


def assert_error(payload: Any, field: str) -> None:
    message = payload.get("error") if isinstance(payload, dict) else str(payload)
    if field not in str(message):
        raise AssertionError(f"Expected error mentioning {field!r}, got {payload!r}")


def signup_body(username: str, password: str, **overrides: Any) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "username": username,
        "email": username,
        "password": password,
        "first_name": "Required",
        "last_name": "Signup",
        "billing_address": "  10 Billing Street  ",
        "phone": "  +441234567890  ",
    }
    body.update(overrides)
    return body


def main() -> int:
    cfg = load_config_from_env()
    client = EstoreClient(cfg.base_url, cfg.timeout)
    run_id = uuid.uuid4().hex[:10]
    created: list[tuple[str, Optional[int]]] = []

    try:
        print("[1/4] Reject missing billing address before creating login...")
        username1 = f"estore-required-bill-{run_id}@example.test"
        invalid = signup_body(username1, cfg.password)
        invalid.pop("billing_address")
        result = client.create_customer(invalid, expected_status=400)
        assert_error(result, "billing_address")

        print("[2/4] Retry same username successfully, proving no Keycloak orphan...")
        valid1 = client.create_customer(signup_body(username1, cfg.password), expected_status=201)
        customer1 = int(valid1["id"])
        created.append((username1, customer1))

        print("[3/4] Reject whitespace-only phone before creating login...")
        username2 = f"estore-required-phone-{run_id}@example.test"
        result = client.create_customer(
            signup_body(username2, cfg.password, phone="   "), expected_status=400,
        )
        assert_error(result, "phone")

        print("[4/4] Retry same username successfully and verify trimmed values...")
        valid2 = client.create_customer(signup_body(username2, cfg.password), expected_status=201)
        customer2 = int(valid2["id"])
        created.append((username2, customer2))
        client.login(username2, cfg.password)
        profile = client.read_customer()
        if profile.get("billing_address") != "10 Billing Street":
            raise AssertionError(f"billing_address was not trimmed: {profile!r}")
        if profile.get("phone") != "+441234567890":
            raise AssertionError(f"phone was not trimmed: {profile!r}")

        print("\nPASS: eStore signup requires billing address and phone before Keycloak creation.")
        return 0
    finally:
        errors: list[str] = []
        for username, customer_id in reversed(created):
            try:
                cleanup_estore_test_customer(username, customer_id, cfg.timeout, label="test11 cleanup")
            except Exception as exc:
                errors.append(f"{username}: {exc}")
        if errors:
            raise AssertionError("Cleanup failed: " + "; ".join(errors))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
