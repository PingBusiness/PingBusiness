#!/usr/bin/env python3
"""Smoke integration test client for the customer-facing estore-app Flask server.

This test reflects the checkout-only order creation design:
  - customer profile create/read/update
  - public store/catalog/inventory reads
  - customer order/order-item/payment reads
  - direct customer order/order-item mutation routes are not available

Orders and order_items are intentionally not created by this test. In the new
flow they are created only through /checkout and successful payment handling.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import requests
from dotenv import load_dotenv

from estore_test_config import estore_base_url, load_test_env

from estore_test_cleanup import cleanup_estore_test_customer

load_test_env()
ExpectedStatus = Union[int, List[int]]


@dataclass
class TestConfig:
    base_url: str
    timeout: int
    username_prefix: str
    password: str


@dataclass
class ResponseResult:
    status_code: int
    payload: Any


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required .env value: {name}")
    return value.strip()


def load_config_from_env() -> TestConfig:
    try:
        timeout = int(os.getenv("ESTORE_APP_TIMEOUT", "20"))
    except ValueError as exc:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be an integer") from exc
    if timeout < 1:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be >= 1")

    return TestConfig(
        base_url=estore_base_url(),
        timeout=timeout,
        username_prefix=os.getenv("ESTORE_TEST_USERNAME_PREFIX", "AUTO_ESTORE_CUSTOMER").strip(),
        password=os.getenv("ESTORE_TEST_PASSWORD", "TestPassword123!").strip(),
    )


class EstoreClient:
    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def headers(self, auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.access_token:
                raise RuntimeError("Authenticated request attempted before login")
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request_result(
        self,
        method: str,
        path: str,
        *,
        expected_status: ExpectedStatus,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> ResponseResult:
        expected = expected_status if isinstance(expected_status, list) else [expected_status]
        response = self.session.request(
            method=method,
            url=self.url(path),
            headers=self.headers(auth=auth),
            json=json_body,
            params=params,
            timeout=self.timeout,
        )
        if response.status_code == 204 or not response.text:
            payload: Any = None
        else:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
        if response.status_code not in expected:
            raise AssertionError(
                f"{method} {path} expected {expected}, got {response.status_code}: "
                f"{json.dumps(payload, default=str)}"
            )
        return ResponseResult(response.status_code, payload)

    def request(self, method: str, path: str, *, expected_status: ExpectedStatus,
                json_body: Optional[Dict[str, Any]] = None,
                params: Optional[Dict[str, Any]] = None,
                auth: bool = True) -> Any:
        return self.request_result(method, path, expected_status=expected_status,
                                   json_body=json_body, params=params, auth=auth).payload

    def health(self) -> Any:
        return self.request("GET", "/health", expected_status=200, auth=False)

    def create_customer(self, body: Dict[str, Any], expected_status: ExpectedStatus = 201) -> Any:
        return self.request("POST", "/customer", expected_status=expected_status, json_body=body, auth=False)

    def login(self, username: str, password: str, expected_status: ExpectedStatus = 200) -> Any:
        payload = self.request("POST", "/login", expected_status=expected_status,
                               json_body={"username": username, "password": password}, auth=False)
        if expected_status == 200:
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not token:
                raise AssertionError(f"Login did not return access_token: {payload!r}")
            self.access_token = token
        return payload

    def read_customer(self) -> Any:
        return self.request("GET", "/customer", expected_status=200)

    def update_customer(self, body: Dict[str, Any], expected_status: ExpectedStatus = 200) -> Any:
        return self.request("POST", "/customer", expected_status=expected_status, json_body=body)

    def get_store(self, store_id: Optional[int] = None, expected_status: ExpectedStatus = 200) -> Any:
        path = "/store" if store_id is None else f"/store/{store_id}"
        return self.request("GET", path, expected_status=expected_status, auth=False)

    def get_products(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/products", expected_status=expected_status, params=params, auth=False)

    def get_product(self, product_id: int, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", f"/product/{product_id}", expected_status=expected_status, auth=False)

    def get_inventories(self, product_id: int, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/inventories", expected_status=expected_status, params={"product_id": product_id}, auth=False)

    def get_orders(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/orders", expected_status=expected_status, params=params)

    def get_order_items(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/order_items", expected_status=expected_status, params=params)

    def get_payments(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/payments", expected_status=expected_status, params=params)

    def assert_order_mutation_routes_unavailable(self) -> None:
        unavailable = [
            ("POST", "/order", {"currency": "CAD"}),
            ("DELETE", "/order/1", None),
            ("POST", "/order_item", {"order_id": 1, "product_id": 1, "quantity": 1}),
            ("DELETE", "/order_item/1", None),
        ]
        for method, path, body in unavailable:
            self.request(method, path, expected_status=[404, 405], json_body=body)


def assert_has_int_id(payload: Any, label: str) -> int:
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
        raise AssertionError(f"{label} did not return integer id: {payload!r}")
    return payload["id"]


def assert_product_files_array(product: Any, label: str) -> None:
    if not isinstance(product, dict):
        raise AssertionError(f"{label} is not a product object: {product!r}")
    if "files" not in product:
        raise AssertionError(f"{label} is missing embedded files array: {product!r}")
    files = product.get("files")
    if not isinstance(files, list):
        raise AssertionError(f"{label}.files is not a list: {files!r}")
    product_id = product.get("id")
    for file_row in files:
        if not isinstance(file_row, dict):
            raise AssertionError(f"{label}.files contains a non-object row: {file_row!r}")
        if file_row.get("product_id") != product_id:
            raise AssertionError(f"{label}.files contains wrong product_id: {file_row!r}")


def assert_estore_catalog_product(product: Any, label: str) -> None:
    assert_product_files_array(product, label)
    if product.get("state") != "A":
        raise AssertionError(f"{label} exposed non-approved product: {product!r}")
    if "review_notes" in product:
        raise AssertionError(f"{label} exposed merchant review notes: {product!r}")


def assert_customer_scoping_rejections(client: EstoreClient) -> None:
    print("  verifying customer scope rejects caller-controlled identity fields...")
    profile = client.read_customer()
    err = client.update_customer({"id": profile["id"], "merchant_id": 999}, expected_status=400)
    if "identity" not in err.get("error", "") and "system-controlled" not in err.get("error", ""):
        raise AssertionError(f"Unexpected update customer error: {err!r}")
    client.assert_order_mutation_routes_unavailable()


def run_suite(config: TestConfig) -> None:
    client = EstoreClient(config.base_url, config.timeout)
    run_id = uuid.uuid4().hex[:12]
    username = f"{config.username_prefix}_{run_id}@example.test".lower()

    customer_id: Optional[int] = None

    try:
        print("[1/7] Health check...")
        health = client.health()
        if health.get("status") != "ok":
            raise AssertionError(f"Unexpected health payload: {health!r}")

        print("[2/7] Create customer with password, login, read/update profile...")
        created_customer = client.create_customer({
            "username": username,
            "email": username,
            "password": config.password,
            "first_name": "Auto",
            "last_name": "Customer",
            "details": "initial customer details",
            "shipping_address": "100 Test Ship Road",
            "billing_address": "100 Test Bill Road",
            "phone": "14165550123",
        })
        customer_id = assert_has_int_id(created_customer, "create customer")
        if not created_customer.get("keycloak_user_id"):
            raise AssertionError(f"create customer missing keycloak_user_id: {created_customer!r}")

        client.login(username, config.password)
        customer = client.read_customer()
        if customer.get("id") != customer_id:
            raise AssertionError(f"read customer returned wrong id: {customer!r}")
        if customer.get("username") != created_customer["keycloak_user_id"]:
            raise AssertionError("BCustomers.username does not match ESTORE Keycloak user id")

        client.update_customer({
            "id": customer_id,
            "first_name": "UpdatedAuto",
            "details": "updated customer details",
            "shipping_address": "101 Updated Ship Road",
            "phone": "14165550999",
        })
        updated = client.read_customer()
        if updated.get("first_name") != "UpdatedAuto" or updated.get("phone") != "14165550999":
            raise AssertionError(f"Customer update not reflected: {updated!r}")
        assert_customer_scoping_rejections(client)

        print("[3/7] Read store and catalog...")
        store = client.get_store()
        if not isinstance(store.get("id"), int):
            raise AssertionError(f"get_store returned unexpected payload: {store!r}")
        products = client.get_products()
        if not isinstance(products, list):
            raise AssertionError(f"GET /products returned non-list payload: {products!r}")
        client.get_products({"state": "D"}, expected_status=403)
        client.get_products({"state": "S"}, expected_status=403)
        client.get_products({"state": "R"}, expected_status=403)
        approved_products = client.get_products({"state": "A"})
        if not isinstance(approved_products, list):
            raise AssertionError(f"GET /products?state=A returned non-list payload: {approved_products!r}")
        for index, catalog_product in enumerate(products):
            assert_estore_catalog_product(catalog_product, f"GET /products row {index}")
        for index, catalog_product in enumerate(approved_products):
            assert_estore_catalog_product(catalog_product, f"GET /products?state=A row {index}")
        if products:
            product = products[0]
            product_id = product.get("id")
            if not isinstance(product_id, int):
                raise AssertionError(f"Product missing id: {product!r}")
            assert_estore_catalog_product(product, "GET /products row")
            fetched_product = client.get_product(product_id)
            if fetched_product.get("id") != product_id:
                raise AssertionError(f"get_product returned wrong product: {fetched_product!r}")
            assert_estore_catalog_product(fetched_product, "GET /product")
            if fetched_product.get("files") != product.get("files"):
                raise AssertionError("GET /product files array does not match GET /products row files array")
            client.request("GET", "/files", expected_status=404, params={"product_id": product_id}, auth=False)
            inventories = client.get_inventories(product_id)
            if not isinstance(inventories, list):
                raise AssertionError(f"get_inventories returned non-list payload: {inventories!r}")
            for inventory in inventories:
                if inventory.get("product_id") != product_id:
                    raise AssertionError(f"get_inventories returned wrong product_id: {inventory!r}")
            total_available = sum(int(i.get("quantity") or 0) for i in inventories if isinstance(i, dict))
            print(f"  availability for product {product_id}: {total_available} across {len(inventories)} location(s)")
        else:
            print("  catalog is empty; approved-only and forbidden-state filters remain valid")

        print("[4/7] Verify direct customer order/order-item mutations are unavailable...")
        client.assert_order_mutation_routes_unavailable()

        print("[5/7] Verify read-only order collections are accessible and empty/new-customer scoped...")
        orders = client.get_orders()
        if not isinstance(orders, list):
            raise AssertionError(f"GET /orders returned non-list payload: {orders!r}")
        order_items = client.get_order_items()
        if not isinstance(order_items, list):
            raise AssertionError(f"GET /order_items returned non-list payload: {order_items!r}")
        for row in order_items:
            if not isinstance(row, dict) or "state" not in row:
                raise AssertionError(f"GET /order_items omitted delivery state: {row!r}")
        payments = client.get_payments()
        if not isinstance(payments, list):
            raise AssertionError(f"GET /payments returned non-list payload: {payments!r}")

        print("[6/7] Verify nonexistent detail reads are cleanly rejected...")
        client.request("GET", "/order/999999999", expected_status=404)
        client.request("GET", "/order_item/999999999", expected_status=404)
        client.request("GET", "/payment/999999999", expected_status=404)

        print("[7/7] Verify customer remains readable...")
        final_customer = client.read_customer()
        if final_customer.get("id") != customer_id:
            raise AssertionError(f"Final customer read returned unexpected payload: {final_customer!r}")

        print("\nPASS: estore-app smoke checks passed.")
    finally:
        cleanup_estore_test_customer(username, customer_id, config.timeout, label="test1 cleanup")


if __name__ == "__main__":
    try:
        run_suite(load_config_from_env())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise
