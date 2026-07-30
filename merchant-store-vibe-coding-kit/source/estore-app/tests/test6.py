#!/usr/bin/env python3
"""Product-review integration test for estore-app.

This test creates a temporary product in the configured estore store and drives
it through review transitions using biz-app. It verifies that estore-app exposes
only approved products and immediately honors admin takedown.

Covered lifecycle:
  D -> S -> D -> S -> A -> D -> S -> A -> D -> S -> R

The final rejected product is removed directly from the test PostgreSQL database,
because rejected state is intentionally terminal in the production API.
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from typing import Any, Dict, Iterable, Optional

import requests
from dotenv import load_dotenv

from estore_test_config import estore_base_url, load_test_env

from estore_review_test_utils import BizReviewClient, delete_products_direct
from estore_test_cleanup import cleanup_estore_test_customer

load_test_env()

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZK1sAAAAASUVORK5CYII="
)


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(f"Missing required .env value: {name}")
    return value


class EstoreClient:
    def __init__(self, timeout: int) -> None:
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

    def create_customer(self, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.request("POST", "/customer", expected_status=201, json_body=body)
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
            raise AssertionError(f"Create customer missing integer id: {payload!r}")
        return payload

    def login(self, username: str, password: str) -> None:
        payload = self.request(
            "POST",
            "/login",
            expected_status=200,
            json_body={"username": username, "password": password},
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"Estore login missing access_token: {payload!r}")
        self.access_token = str(token)


def product_ids(payload: Any) -> set[int]:
    if not isinstance(payload, list):
        raise AssertionError(f"Expected product list, got {payload!r}")
    result: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise AssertionError(f"Product list contains non-object: {item!r}")
        if item.get("state") != "A":
            raise AssertionError(f"Estore list exposed non-approved product: {item!r}")
        if "review_notes" in item:
            raise AssertionError(f"Estore list exposed review_notes: {item!r}")
        if isinstance(item.get("id"), int):
            result.add(int(item["id"]))
    return result


def assert_hidden(estore: EstoreClient, product_id: int, file_id: int, label: str) -> None:
    listed = estore.request("GET", "/products", expected_status=200)
    if product_id in product_ids(listed):
        raise AssertionError(f"{label}: product remained in estore list")
    estore.request("GET", f"/product/{product_id}", expected_status=404)
    estore.request("GET", "/inventories", expected_status=404, params={"product_id": product_id})
    estore.request("GET", f"/file/{file_id}", expected_status=404)


def assert_estore_product(
    estore: EstoreClient,
    product_id: int,
    *,
    expected_name: str,
    expected_amount: str,
    file_id: int,
) -> Dict[str, Any]:
    listed = estore.request("GET", "/products", expected_status=200)
    ids = product_ids(listed)
    if product_id not in ids:
        raise AssertionError(f"Approved product {product_id} missing from estore list: {listed!r}")
    product = estore.request("GET", f"/product/{product_id}", expected_status=200)
    if not isinstance(product, dict):
        raise AssertionError(f"Direct product response is not an object: {product!r}")
    if product.get("state") != "A":
        raise AssertionError(f"Direct product is not approved: {product!r}")
    if product.get("name") != expected_name:
        raise AssertionError(f"Unexpected product name: {product!r}")
    if str(product.get("amount")) != expected_amount:
        raise AssertionError(f"Unexpected product amount: {product!r}")
    if "review_notes" in product:
        raise AssertionError(f"Direct product exposed review_notes: {product!r}")
    files = product.get("files")
    if not isinstance(files, list) or file_id not in {
        int(row["id"]) for row in files if isinstance(row, dict) and isinstance(row.get("id"), int)
    }:
        raise AssertionError(f"Approved product did not expose its file: {product!r}")
    file_payload = estore.request("GET", f"/file/{file_id}", expected_status=200)
    if not isinstance(file_payload, dict) or file_payload.get("product_id") != product_id:
        raise AssertionError(f"Unexpected estore file payload: {file_payload!r}")
    inventories = estore.request(
        "GET",
        "/inventories",
        expected_status=200,
        params={"product_id": product_id},
    )
    if not isinstance(inventories, list):
        raise AssertionError(f"Inventory response is not a list: {inventories!r}")
    return product


def main() -> int:
    timeout = int(env("ESTORE_APP_TIMEOUT", "30") or "30")
    estore = EstoreClient(timeout)
    admin = BizReviewClient(timeout)
    manager: Optional[BizReviewClient] = None
    run_id = uuid.uuid4().hex[:12]
    manager_username = f"auto_estore_review_manager_{run_id}@example.test"
    manager_password = f"T!{uuid.uuid4().hex}9a"
    customer_username = f"auto_estore_review_customer_{run_id}@example.test"
    customer_password = env("ESTORE_TEST_PASSWORD", "TestPassword123!") or "TestPassword123!"

    manager_id: Optional[int] = None
    customer_id: Optional[int] = None
    product_id: Optional[int] = None
    file_id: Optional[int] = None

    try:
        print("[1/12] Resolve the configured estore store and authenticate biz admin...")
        store = estore.request("GET", "/store", expected_status=200)
        if not isinstance(store, dict) or not isinstance(store.get("id"), int) or not isinstance(store.get("merchant_id"), int):
            raise AssertionError(f"Configured estore store payload is invalid: {store!r}")
        store_id = int(store["id"])
        merchant_id = int(store["merchant_id"])
        admin.login_admin()

        print("[2/12] Create a temporary manager and draft product in the configured store...")
        manager_row = admin.request(
            "POST",
            "/user",
            expected_status=201,
            json_body={
                "username": manager_username,
                "password": manager_password,
                "merchant_id": merchant_id,
                "user_type": "M",
                "details": f"estore product-review test {run_id}",
            },
        )
        manager_id = int(manager_row["id"])
        manager = admin.login_user(manager_username, manager_password)

        initial_name = f"AUTO_ESTORE_REVIEW_{run_id}"
        created = manager.request(
            "POST",
            "/product",
            expected_status=201,
            json_body={
                "store_id": store_id,
                "name": initial_name,
                "details": "estore review integration product",
                "description": "draft product hidden from estore",
                "identifier": str(uuid.uuid4()),
                "amount": "12.34",
                "currency": "HKD",
            },
        )
        product_id = int(created["id"])
        created_product = manager.request(
            "GET",
            f"/product/{product_id}",
            expected_status=200,
        )
        if not isinstance(created_product, dict) or created_product.get("state") != "D":
            raise AssertionError(
                f"New product was not Draft after authoritative re-read: {created_product!r}"
            )
        created_file = manager.request(
            "POST",
            "/file",
            expected_status=201,
            json_body={
                "product_id": product_id,
                "name": "review-test.png",
                "description": "review framework test image",
                "mime_type": "image/png",
                "file_content": base64.b64encode(PNG_BYTES).decode("ascii"),
            },
        )
        file_id = int(created_file["id"])
        assert_hidden(estore, product_id, file_id, "draft")
        estore.request("GET", "/products", expected_status=403, params={"state": "D"})
        estore.request("GET", "/products", expected_status=403, params={"state": "S"})
        estore.request("GET", "/products", expected_status=403, params={"state": "R"})

        print("[3/12] Submit the product; Submitted remains hidden...")
        submitted = manager.request(
            "POST",
            "/submit_product/",
            expected_status=200,
            json_body={"product_id": product_id},
        )
        if submitted.get("state") != "S":
            raise AssertionError(f"Product was not submitted: {submitted!r}")
        assert_hidden(estore, product_id, file_id, "submitted")

        print("[4/12] Admin requests changes; Draft remains hidden and notes stay merchant-facing...")
        returned = admin.request(
            "POST",
            "/product_state/",
            expected_status=200,
            json_body={
                "product_id": product_id,
                "state": "D",
                "review_notes": "Please revise the storefront description",
            },
        )
        if returned.get("state") != "D":
            raise AssertionError(f"Product was not returned to Draft: {returned!r}")
        manager_view = manager.request("GET", f"/product/{product_id}", expected_status=200)
        if manager_view.get("review_notes") != "Please revise the storefront description":
            raise AssertionError(f"Manager could not see review notes: {manager_view!r}")
        assert_hidden(estore, product_id, file_id, "returned draft")

        print("[5/12] Revise, resubmit, approve, and create inventory...")
        manager.request(
            "POST",
            "/product",
            expected_status=200,
            json_body={"id": product_id, "description": "approved storefront description"},
        )
        manager.request(
            "POST",
            "/submit_product/",
            expected_status=200,
            json_body={"product_id": product_id},
        )
        approved = admin.request(
            "POST",
            "/product_state/",
            expected_status=200,
            json_body={
                "product_id": product_id,
                "state": "A",
                "review_notes": "Approved for storefront publication",
            },
        )
        if approved.get("state") != "A":
            raise AssertionError(f"Product was not approved: {approved!r}")
        inventory = manager.request(
            "POST",
            "/inventory",
            expected_status=201,
            json_body={"product_id": product_id, "quantity": 5, "location": "MAIN"},
        )
        if not isinstance(inventory.get("id"), int):
            raise AssertionError(f"Inventory creation failed: {inventory!r}")

        print("[6/12] Approved product, file, and inventory are visible; review notes are not...")
        assert_estore_product(
            estore,
            product_id,
            expected_name=initial_name,
            expected_amount="12.34",
            file_id=file_id,
        )
        approved_only = estore.request("GET", "/products", expected_status=200, params={"state": "A"})
        if product_id not in product_ids(approved_only):
            raise AssertionError(f"state=A did not include approved product: {approved_only!r}")

        print("[7/12] Create a customer for checkout-boundary validation...")
        created_customer = estore.create_customer({
            "username": customer_username,
            "email": customer_username,
            "password": customer_password,
            "first_name": "Review",
            "last_name": "Customer",
            "details": "estore review test customer",
            "shipping_address": "100 Review Test Road",
            "billing_address": "100 Review Test Road",
            "phone": "14165550123",
        })
        customer_id = int(created_customer["id"])
        estore.login(customer_username, customer_password)
        payment_configuration = estore.request("GET", "/payment_networks", expected_status=200, auth=False)
        payment_networks = payment_configuration.get("payment_networks") if isinstance(payment_configuration, dict) else None
        if not isinstance(payment_networks, list) or not payment_networks:
            raise AssertionError(f"Invalid /payment_networks response: {payment_configuration!r}")
        payment_network = payment_networks[0]

        print("[8/12] Admin takedown A -> D immediately hides all storefront paths...")
        taken_down = admin.request(
            "POST",
            "/product_state/",
            expected_status=200,
            json_body={
                "product_id": product_id,
                "state": "D",
                "review_notes": "Emergency storefront takedown",
            },
        )
        if taken_down.get("state") != "D":
            raise AssertionError(f"Product takedown failed: {taken_down!r}")
        assert_hidden(estore, product_id, file_id, "emergency takedown")
        estore.request(
            "POST",
            "/checkout",
            expected_status=404,
            json_body={
                "network": payment_network,
                "cart": [{"product_id": product_id, "quantity": 1}],
                "customer_state": "HK",
                "customer_country": "HK",
                "customer_postal_code": "000000",
            },
            auth=True,
        )

        print("[9/12] Modify the taken-down draft, resubmit, and reapprove...")
        revised_name = f"{initial_name}_REVISED"
        manager.request(
            "POST",
            "/product",
            expected_status=200,
            json_body={"id": product_id, "name": revised_name, "amount": "15.67"},
        )
        manager.request(
            "POST",
            "/submit_product/",
            expected_status=200,
            json_body={"product_id": product_id},
        )
        admin.request(
            "POST",
            "/product_state/",
            expected_status=200,
            json_body={
                "product_id": product_id,
                "state": "A",
                "review_notes": "Reapproved after remediation",
            },
        )

        print("[10/12] Reapproved product exposes current data and retained inventory...")
        assert_estore_product(
            estore,
            product_id,
            expected_name=revised_name,
            expected_amount="15.67",
            file_id=file_id,
        )

        print("[11/12] Take down again, submit, and reject; Rejected remains hidden...")
        admin.request(
            "POST",
            "/product_state/",
            expected_status=200,
            json_body={"product_id": product_id, "state": "D", "review_notes": "Final review required"},
        )
        manager.request(
            "POST",
            "/submit_product/",
            expected_status=200,
            json_body={"product_id": product_id},
        )
        rejected = admin.request(
            "POST",
            "/product_state/",
            expected_status=200,
            json_body={"product_id": product_id, "state": "R", "review_notes": "Rejected by compliance"},
        )
        if rejected.get("state") != "R":
            raise AssertionError(f"Product rejection failed: {rejected!r}")
        assert_hidden(estore, product_id, file_id, "rejected")

        print("[12/12] Review-framework estore checks passed.")
        print("\nPASS: estore-app exposes only approved products and honors review takedown.")
        return 0
    finally:
        cleanup_errors: list[str] = []
        if product_id is not None:
            try:
                delete_products_direct([product_id])
            except Exception as exc:
                cleanup_errors.append(f"product {product_id}: {exc}")
        if manager_id is not None and admin.access_token:
            try:
                admin.request("DELETE", f"/user/{manager_id}", expected_status=(200, 404))
            except Exception as exc:
                cleanup_errors.append(f"manager {manager_id}: {exc}")
        try:
            cleanup_estore_test_customer(
                customer_username,
                customer_id,
                timeout,
                label="test6 cleanup",
                require_biz_cleanup=customer_id is not None,
            )
        except Exception as exc:
            cleanup_errors.append(f"customer {customer_id}: {exc}")
        if cleanup_errors:
            raise AssertionError("Cleanup failed: " + "; ".join(cleanup_errors))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise
