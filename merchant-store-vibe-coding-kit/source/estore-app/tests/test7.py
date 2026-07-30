#!/usr/bin/env python3
"""Customer-facing order-item delivery-state integration test for estore-app.

The test creates an approved product fixture, a storefront customer, an order,
and one order item. It verifies that estore-app exposes the initial NULL state,
then exposes D after a merchant manager marks the item Delivered through biz-app.
The storefront has no delivery-state mutation endpoint.
"""
from __future__ import annotations

import sys
import uuid
from typing import Any, Dict, Iterable, Optional

import requests

from estore_test_config import estore_base_url, load_test_env
from estore_review_test_utils import ApprovedProductFixture, delete_orders_direct
from estore_test_cleanup import cleanup_estore_test_customer

load_test_env()


class EstoreClient:
    def __init__(self, timeout: int = 30) -> None:
        self.base_url = estore_base_url()
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | Iterable[int],
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = False,
    ) -> Any:
        expected = {expected_status} if isinstance(expected_status, int) else set(expected_status)
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.access_token:
                raise RuntimeError("Authenticated estore request attempted before login")
            headers["Authorization"] = f"Bearer {self.access_token}"
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            json=json_body,
            params=params,
            timeout=self.timeout,
        )
        try:
            payload: Any = response.json() if response.text else None
        except ValueError:
            payload = response.text
        if response.status_code not in expected:
            raise AssertionError(
                f"{method} {path} expected {sorted(expected)}, got "
                f"{response.status_code}: {payload!r}"
            )
        return payload

    def login(self, username: str, password: str) -> None:
        payload = self.request(
            "POST", "/login", expected_status=200,
            json_body={"username": username, "password": password},
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"Estore login missing access_token: {payload!r}")
        self.access_token = str(token)


def assert_state(payload: Any, expected: Optional[str], label: str) -> None:
    if not isinstance(payload, dict):
        raise AssertionError(f"{label}: expected object, got {payload!r}")
    if "state" not in payload:
        raise AssertionError(f"{label}: state field was omitted: {payload!r}")
    if payload.get("state") != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {payload.get('state')!r}")


def main() -> int:
    timeout = 30
    estore = EstoreClient(timeout)
    fixture: Optional[ApprovedProductFixture] = None
    customer_username = f"auto_estore_delivery_{uuid.uuid4().hex[:12]}@example.test"
    customer_password = "TestPassword123!"
    customer_id: Optional[int] = None
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None

    try:
        print("[1/7] Create an approved product fixture in the configured store...")
        fixture = ApprovedProductFixture.create(estore.base_url, timeout, quantity=5)

        print("[2/7] Create and authenticate a temporary storefront customer...")
        created_customer = estore.request(
            "POST", "/customer", expected_status=201,
            json_body={
                "username": customer_username,
                "email": customer_username,
                "password": customer_password,
                "first_name": "Delivery",
                "last_name": "Tester",
                "shipping_address": "1 Test Street",
                "billing_address": "1 Test Street",
                "phone": "14165550123",
            },
        )
        customer_id = int(created_customer["id"])
        estore.login(customer_username, customer_password)

        print("[3/7] Create an order and order item through biz-app...")
        order = fixture.admin.request(
            "POST", "/order", expected_status=201,
            json_body={
                "customer_id": customer_id,
                "store_id": fixture.store_id,
                "status": "S",
                "currency": "HKD",
                "subtotal_amount": "12.34",
                "total_amount": "12.34",
                "details": "estore order-item delivery-state test",
            },
        )
        order_id = int(order["id"])
        item = fixture.admin.request(
            "POST", "/order_item", expected_status=201,
            json_body={
                "order_id": order_id,
                "product_id": fixture.product_id,
                "quantity": 1,
                "unit_amount": "12.34",
                "amount": "12.34",
                "details": "delivery-state line item",
            },
        )
        order_item_id = int(item["id"])

        print("[4/7] Verify estore list and direct reads expose the initial NULL state...")
        listed = estore.request(
            "GET", "/order_items", expected_status=200,
            params={"order_id": order_id}, auth=True,
        )
        if not isinstance(listed, list) or len(listed) != 1:
            raise AssertionError(f"Expected one storefront order item: {listed!r}")
        assert_state(listed[0], None, "estore list initial state")
        if listed[0].get("order_status") != "S":
            raise AssertionError(f"Expected Successful parent order: {listed[0]!r}")
        direct = estore.request(
            "GET", f"/order_item/{order_item_id}", expected_status=200, auth=True,
        )
        assert_state(direct, None, "estore direct initial state")

        print("[5/7] Mark the item Delivered through the merchant manager API...")
        delivered = fixture.manager.request(
            "POST", "/order_item_state/", expected_status=200,
            json_body={"order_item_id": order_item_id, "state": "D"},
        )
        assert_state(delivered, "D", "manager delivery response")

        print("[6/7] Verify estore list and direct reads now expose Delivered...")
        listed = estore.request(
            "GET", "/order_items", expected_status=200,
            params={"order_id": order_id}, auth=True,
        )
        if not isinstance(listed, list) or len(listed) != 1:
            raise AssertionError(f"Expected one storefront order item after delivery: {listed!r}")
        assert_state(listed[0], "D", "estore list delivered state")
        direct = estore.request(
            "GET", f"/order_item/{order_item_id}", expected_status=200, auth=True,
        )
        assert_state(direct, "D", "estore direct delivered state")
        if direct.get("order_status") != "S":
            raise AssertionError(f"Delivered item lost Successful parent status: {direct!r}")

        print("[7/7] Verify the storefront does not expose a state-mutation route...")
        estore.request(
            "POST", "/order_item_state/", expected_status=(404, 405),
            json_body={"order_item_id": order_item_id, "state": "D"}, auth=True,
        )

        print("\nPASS: estore-app exposes order-item delivery state as read-only customer data.")
        return 0

    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise

    finally:
        cleanup_errors: list[str] = []
        if order_id is not None:
            try:
                delete_orders_direct([order_id])
            except Exception as exc:
                cleanup_errors.append(f"order {order_id}: {exc}")
        try:
            cleanup_estore_test_customer(
                customer_username,
                customer_id,
                timeout,
                label="test7 cleanup",
                require_biz_cleanup=True,
            )
        except Exception as exc:
            cleanup_errors.append(f"customer cleanup: {exc}")
        if fixture is not None:
            try:
                fixture.cleanup()
            except Exception as exc:
                cleanup_errors.append(f"fixture cleanup: {exc}")
        if cleanup_errors:
            raise AssertionError("Cleanup failed: " + "; ".join(cleanup_errors))


if __name__ == "__main__":
    raise SystemExit(main())
