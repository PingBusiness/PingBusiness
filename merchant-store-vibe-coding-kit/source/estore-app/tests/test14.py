#!/usr/bin/env python3
"""Customer subscription-cancellation ownership integration test.

This test never invokes PaymentAsia. It creates ordinary order items so the
owning customer reaches biz-app's recurring validation (409), while a different
customer must be rejected by estore-app (403) before the cancellation proxy is
called.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any, Dict, Optional

import requests

from estore_review_test_utils import ApprovedProductFixture, delete_orders_direct
from estore_test_cleanup import cleanup_estore_test_customer
from estore_test_config import estore_base_url, load_test_env

load_test_env()


class CustomerClient:
    def __init__(self, base_url: str, timeout: int, label: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.label = label
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.username: Optional[str] = None
        self.customer_id: Optional[int] = None

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        body: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.access_token:
                raise RuntimeError(f"{self.label}: authenticated request before login")
            headers["Authorization"] = f"Bearer {self.access_token}"
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            json=body,
            timeout=self.timeout,
        )
        if response.status_code == 204 or not response.text:
            payload: Any = None
        else:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
        if response.status_code != expected_status:
            raise AssertionError(
                f"{self.label}: {method} {path} expected {expected_status}, got "
                f"{response.status_code}: {json.dumps(payload, default=str)}"
            )
        return payload

    def create(self, username: str, password: str) -> None:
        payload = self.request(
            "POST",
            "/customer",
            expected_status=201,
            auth=False,
            body={
                "username": username,
                "email": username,
                "password": password,
                "first_name": self.label,
                "last_name": "CancellationTest",
                "details": f"{self.label} customer cancellation test",
                "shipping_address": "1 Test Street",
                "billing_address": "1 Test Street",
                "phone": "14165550123",
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
            raise AssertionError(f"{self.label}: customer creation missing integer id: {payload!r}")
        self.username = username
        self.customer_id = int(payload["id"])

    def login(self, password: str) -> None:
        if not self.username:
            raise RuntimeError(f"{self.label}: login before customer creation")
        payload = self.request(
            "POST",
            "/login",
            expected_status=200,
            auth=False,
            body={"username": self.username, "password": password},
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"{self.label}: login missing access token: {payload!r}")
        self.access_token = str(token)

    def cancel(self, order_item_id: int, expected_status: int) -> Any:
        return self.request(
            "POST",
            f"/order_item/{order_item_id}/recurring/cancel",
            expected_status=expected_status,
            body={},
        )


def expect_error_contains(payload: Any, needle: str, label: str) -> None:
    if not isinstance(payload, dict) or needle.lower() not in str(payload.get("error", "")).lower():
        raise AssertionError(f"{label}: expected {needle!r}, got {payload!r}")


def main() -> int:
    timeout = int(os.getenv("ESTORE_APP_TIMEOUT", "20"))
    base_url = estore_base_url()
    run_id = uuid.uuid4().hex[:10]
    password = os.getenv("ESTORE_TEST_PASSWORD", "TestPassword123!")
    owner = CustomerClient(base_url, timeout, "owner")
    other = CustomerClient(base_url, timeout, "other")
    fixture: Optional[ApprovedProductFixture] = None
    order_ids: list[int] = []

    try:
        print("[1/5] Create an approved ordinary product fixture...")
        fixture = ApprovedProductFixture.create(base_url, timeout, quantity=5, amount="12.34")

        print("[2/5] Create and authenticate two customers in the same estore...")
        owner.create(f"auto-cancel-owner-{run_id}@example.test", password)
        other.create(f"auto-cancel-other-{run_id}@example.test", password)
        owner.login(password)
        other.login(password)

        if owner.customer_id is None or other.customer_id is None:
            raise AssertionError("Customer IDs were not created")

        print("[3/5] Seed one ordinary order item owned by the first customer...")
        order = fixture.admin.request(
            "POST",
            "/order",
            expected_status=201,
            json_body={
                "customer_id": owner.customer_id,
                "store_id": fixture.store_id,
                "status": "S",
                "currency": "HKD",
                "subtotal_amount": 12.34,
                "total_amount": 12.34,
                "details": f"customer cancellation ownership test {run_id}",
            },
        )
        order_id = int(order["id"])
        order_ids.append(order_id)
        item = fixture.admin.request(
            "POST",
            "/order_item",
            expected_status=201,
            json_body={
                "order_id": order_id,
                "product_id": fixture.product_id,
                "quantity": 1,
                "unit_amount": 12.34,
                "amount": 12.34,
                "details": f"ordinary cancellation ownership item {run_id}",
            },
        )
        order_item_id = int(item["id"])

        print("[4/5] Owning customer reaches biz-app recurring validation...")
        owner_result = owner.cancel(order_item_id, expected_status=409)
        expect_error_contains(owner_result, "not recurring", "owner cancellation")

        print("[5/5] Different customer is blocked by estore-app ownership validation...")
        other_result = other.cancel(order_item_id, expected_status=403)
        expect_error_contains(other_result, "outside the current customer scope", "cross-customer cancellation")

        print("\nPASS: eStore customer cancellation enforces order-item ownership.")
        return 0
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise
    finally:
        if order_ids:
            try:
                delete_orders_direct(order_ids)
            except Exception as exc:
                print(f"  cleanup warning orders {order_ids}: {exc}", file=sys.stderr)
        for client in (owner, other):
            if client.username or client.customer_id:
                try:
                    cleanup_estore_test_customer(
                        client.username,
                        client.customer_id,
                        timeout,
                        label=f"{client.label} cancellation test cleanup",
                    )
                except Exception as exc:
                    print(f"  cleanup warning {client.label} customer: {exc}", file=sys.stderr)
        if fixture is not None:
            try:
                fixture.cleanup()
            except Exception as exc:
                print(f"  cleanup warning product fixture: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
