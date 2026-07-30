#!/usr/bin/env python3
"""Customer-visible delivery integrity test for estore-app and biz-app.

Verifies that pending orders cannot be delivered, that delivery becomes available
only after the order is Successful, and that the delivered line item and its
parent-order success state become immutable while remaining visible to the
storefront customer.
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


def expect_error(payload: Any, needle: str, label: str) -> None:
    if not isinstance(payload, dict) or needle.lower() not in str(payload.get("error", "")).lower():
        raise AssertionError(f"{label}: expected {needle!r}, got {payload!r}")


def main() -> int:
    timeout = 30
    estore = EstoreClient(timeout)
    fixture: Optional[ApprovedProductFixture] = None
    customer_username = f"auto_estore_delivery_integrity_{uuid.uuid4().hex[:10]}@example.test"
    customer_password = "TestPassword123!"
    customer_id: Optional[int] = None
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None

    try:
        print("[1/9] Create an approved product fixture and storefront customer...")
        fixture = ApprovedProductFixture.create(estore.base_url, timeout, quantity=5)
        created_customer = estore.request(
            "POST", "/customer", expected_status=201,
            json_body={
                "username": customer_username,
                "email": customer_username,
                "password": customer_password,
                "first_name": "Delivery",
                "last_name": "Integrity",
                "shipping_address": "1 Test Street",
                "billing_address": "1 Test Street",
                "phone": "14165550123",
            },
        )
        customer_id = int(created_customer["id"])
        estore.login(customer_username, customer_password)

        print("[2/9] Create a Pending order and undelivered line item...")
        order = fixture.admin.request(
            "POST", "/order", expected_status=201,
            json_body={
                "customer_id": customer_id,
                "store_id": fixture.store_id,
                "status": "N",
                "currency": "HKD",
                "subtotal_amount": "12.34",
                "total_amount": "12.34",
                "details": "estore delivery-integrity pending order",
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
                "details": "delivery-integrity line item",
            },
        )
        order_item_id = int(item["id"])

        print("[3/9] Verify the customer sees an undelivered Pending-order item...")
        initial = estore.request(
            "GET", f"/order_item/{order_item_id}", expected_status=200, auth=True,
        )
        if initial.get("state") is not None or initial.get("order_status") != "N":
            raise AssertionError(f"Unexpected initial item: {initial!r}")

        print("[4/9] Reject delivery while the parent order is Pending...")
        rejected = fixture.manager.request(
            "POST", "/order_item_state/", expected_status=409,
            json_body={"order_item_id": order_item_id, "state": "D"},
        )
        expect_error(rejected, "successful orders", "pending delivery rejection")
        unchanged = estore.request(
            "GET", f"/order_item/{order_item_id}", expected_status=200, auth=True,
        )
        if unchanged.get("state") is not None:
            raise AssertionError(f"Pending item changed after rejected delivery: {unchanged!r}")

        print("[5/9] Mark the order Successful and then deliver the item...")
        fixture.admin.request(
            "POST", "/order", expected_status=200,
            json_body={"id": order_id, "status": "S"},
        )
        delivered = fixture.manager.request(
            "POST", "/order_item_state/", expected_status=200,
            json_body={"order_item_id": order_item_id, "state": "D"},
        )
        if delivered.get("state") != "D" or delivered.get("order_status") != "S":
            raise AssertionError(f"Delivery transition failed: {delivered!r}")

        print("[6/9] Reject edits and deletion of the Delivered item...")
        update_rejected = fixture.admin.request(
            "POST", "/order_item", expected_status=409,
            json_body={"id": order_item_id, "quantity": 2, "details": "must not change"},
        )
        expect_error(update_rejected, "cannot be modified", "delivered update rejection")
        delete_rejected = fixture.admin.request(
            "DELETE", f"/order_item/{order_item_id}", expected_status=409,
        )
        expect_error(delete_rejected, "cannot be deleted", "delivered delete rejection")

        print("[7/9] Reject parent-order downgrade and deletion...")
        downgrade_rejected = fixture.admin.request(
            "POST", "/order", expected_status=409,
            json_body={"id": order_id, "status": "F"},
        )
        expect_error(downgrade_rejected, "must remain successful", "order downgrade rejection")
        order_delete_rejected = fixture.admin.request(
            "DELETE", f"/order/{order_id}", expected_status=409,
        )
        expect_error(order_delete_rejected, "cannot be deleted", "order delete rejection")

        print("[8/9] Verify the customer still sees the immutable Delivered record...")
        direct = estore.request(
            "GET", f"/order_item/{order_item_id}", expected_status=200, auth=True,
        )
        if direct.get("state") != "D" or direct.get("order_status") != "S":
            raise AssertionError(f"Customer delivery record is inconsistent: {direct!r}")
        listed = estore.request(
            "GET", "/order_items", expected_status=200,
            params={"order_id": order_id}, auth=True,
        )
        if not isinstance(listed, list) or len(listed) != 1 or listed[0].get("state") != "D":
            raise AssertionError(f"Customer order-item list is inconsistent: {listed!r}")

        print("[9/9] Verify storefront remains read-only...")
        estore.request(
            "POST", "/order_item_state/", expected_status=(404, 405),
            json_body={"order_item_id": order_item_id, "state": "D"}, auth=True,
        )

        print("\nPASS: estore delivery gating and immutable Delivered-record checks passed.")
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
                label="test8 cleanup",
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
