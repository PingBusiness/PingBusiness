#!/usr/bin/env python3
"""Negative/edge integration tests for the customer-facing estore-app.

This version reflects the checkout-only order creation design:
  - customers cannot POST/DELETE /order or /order_item directly
  - customer profile, catalog, token, scoping, duplicate-registration, rollback,
    and password-security checks remain covered
  - read-only order/order-item/payment endpoints remain available

Order/order_item creation is intentionally not tested here. It belongs to the
checkout/payment callback flow, not customer-facing direct mutation routes.
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
        username_prefix=os.getenv("ESTORE_TEST_USERNAME_PREFIX", "AUTO_ESTORE_NEG").strip(),
        password=os.getenv("ESTORE_TEST_PASSWORD", "TestPassword123!").strip(),
    )


class EstoreClient:
    def __init__(self, base_url: str, timeout: int, label: str):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.label = label
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.username: Optional[str] = None
        self.customer_id: Optional[int] = None
        self.keycloak_user_id: Optional[str] = None

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def headers(self, *, auth: bool = True, invalid_token: bool = False) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth:
            if invalid_token:
                headers["Authorization"] = "Bearer definitely.invalid.customer.token"
            else:
                if not self.access_token:
                    raise RuntimeError(f"{self.label}: authenticated request before login")
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
        invalid_token: bool = False,
    ) -> ResponseResult:
        expected = expected_status if isinstance(expected_status, list) else [expected_status]
        response = self.session.request(
            method=method,
            url=self.url(path),
            headers=self.headers(auth=auth, invalid_token=invalid_token),
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
                f"{self.label}: {method} {path} expected {expected}, got {response.status_code}: "
                f"{json.dumps(payload, default=str)}"
            )
        return ResponseResult(response.status_code, payload)

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: ExpectedStatus,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        invalid_token: bool = False,
    ) -> Any:
        return self.request_result(
            method,
            path,
            expected_status=expected_status,
            json_body=json_body,
            params=params,
            auth=auth,
            invalid_token=invalid_token,
        ).payload

    def health(self) -> Any:
        return self.request("GET", "/health", expected_status=200, auth=False)

    def create_customer(self, body: Dict[str, Any], expected_status: ExpectedStatus = 201) -> Any:
        payload = self.request("POST", "/customer", expected_status=expected_status, json_body=body, auth=False)
        if expected_status == 201:
            self.customer_id = assert_int_id(payload, f"{self.label} create_customer")
            self.keycloak_user_id = payload.get("keycloak_user_id")
        return payload

    def login(self, username: str, password: str, expected_status: ExpectedStatus = 200) -> Any:
        payload = self.request(
            "POST",
            "/login",
            expected_status=expected_status,
            json_body={"username": username, "password": password},
            auth=False,
        )
        if expected_status == 200:
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not token:
                raise AssertionError(f"{self.label}: login missing access_token: {payload!r}")
            self.access_token = token
            self.username = username
        return payload

    def read_customer(self, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", "/customer", expected_status=expected_status, **kwargs)

    def update_customer(self, body: Dict[str, Any], expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("POST", "/customer", expected_status=expected_status, json_body=body, **kwargs)

    def update_password(self, body: Dict[str, Any], expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("POST", "/customer/update_password", expected_status=expected_status, json_body=body, **kwargs)

    def get_store(self, store_id: Optional[int] = None, expected_status: ExpectedStatus = 200) -> Any:
        path = "/store" if store_id is None else f"/store/{store_id}"
        return self.request("GET", path, expected_status=expected_status, auth=False)

    def get_products(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/products", expected_status=expected_status, params=params, auth=False)

    def get_product(self, product_id: int, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", f"/product/{product_id}", expected_status=expected_status, auth=False)

    def get_inventories(self, product_id: int, expected_status: ExpectedStatus = 200) -> Any:
        return self.request("GET", "/inventories", expected_status=expected_status, params={"product_id": product_id}, auth=False)

    def get_orders(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", "/orders", expected_status=expected_status, params=params, **kwargs)

    def get_order(self, order_id: int, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", f"/order/{order_id}", expected_status=expected_status, **kwargs)

    def get_order_items(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", "/order_items", expected_status=expected_status, params=params, **kwargs)

    def get_order_item(self, item_id: int, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", f"/order_item/{item_id}", expected_status=expected_status, **kwargs)

    def get_payments(self, params: Optional[Dict[str, Any]] = None, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", "/payments", expected_status=expected_status, params=params, **kwargs)

    def get_payment(self, payment_id: int, expected_status: ExpectedStatus = 200, **kwargs: Any) -> Any:
        return self.request("GET", f"/payment/{payment_id}", expected_status=expected_status, **kwargs)

    def assert_order_mutation_routes_unavailable(self) -> None:
        unavailable = [
            ("POST", "/order", {"currency": "CAD"}),
            ("DELETE", "/order/1", None),
            ("POST", "/order_item", {"order_id": 1, "product_id": 1, "quantity": 1}),
            ("DELETE", "/order_item/1", None),
            ("POST", "/payment", {"order_id": 1, "currency": "CAD", "amount": 1, "status": "S"}),
        ]
        for method, path, body in unavailable:
            self.request(method, path, expected_status=[404, 405], json_body=body)


def assert_int_id(payload: Any, label: str) -> int:
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
        raise AssertionError(f"{label}: missing integer id in {payload!r}")
    return int(payload["id"])


def make_customer_body(username: str, password: str, label: str) -> Dict[str, Any]:
    return {
        "username": username,
        "email": username,
        "password": password,
        "first_name": f"{label}First",
        "last_name": f"{label}Last",
        "details": f"{label} test customer",
        "shipping_address": f"{label} Test Ship Road",
        "billing_address": f"{label} Test Bill Road",
        "phone": "14165550123",
    }


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


def first_seed_product(client: EstoreClient) -> Optional[Dict[str, Any]]:
    products = client.get_products()
    if not isinstance(products, list):
        raise AssertionError(f"GET /products returned non-list payload: {products!r}")
    if not products:
        return None
    product = products[0]
    if not isinstance(product.get("id"), int):
        raise AssertionError(f"Seed product missing integer id: {product!r}")
    assert_estore_catalog_product(product, "GET /products row")
    fetched_product = client.get_product(product["id"])
    assert_estore_catalog_product(fetched_product, "GET /product")
    if fetched_product.get("files") != product.get("files"):
        raise AssertionError("GET /product files array does not match GET /products row files array")
    client.request("GET", "/files", expected_status=404, params={"product_id": product["id"]}, auth=False)
    return product


def assert_missing_and_invalid_tokens(client: EstoreClient) -> None:
    print("[4/9] Missing/invalid customer token checks across active customer-scoped routes...")
    missing_calls = [
        ("GET", "/customer", None),
        ("POST", "/customer", {"id": 1, "first_name": "NoAuth"}),
        ("POST", "/customer/update_password", {"current_password": "old", "new_password": "new-password-123"}),
        ("GET", "/orders", None),
        ("GET", "/order/1", None),
        ("GET", "/order_items", None),
        ("GET", "/order_item/1", None),
        ("GET", "/payments", None),
        ("GET", "/payment/1", None),
    ]

    for method, path, body in missing_calls:
        client.request(method, path, expected_status=401, json_body=body, auth=False)
        client.request(method, path, expected_status=401, json_body=body, invalid_token=True)

    # Removed mutation routes should stay unavailable, not merely unauthorized.
    removed_mutations = [
        ("POST", "/order", {"currency": "CAD"}),
        ("DELETE", "/order/1", None),
        ("POST", "/order_item", {"order_id": 1, "product_id": 1, "quantity": 1}),
        ("DELETE", "/order_item/1", None),
        ("POST", "/payment", {"order_id": 1, "currency": "CAD", "amount": 1, "status": "S"}),
    ]
    for method, path, body in removed_mutations:
        client.request(method, path, expected_status=[404, 405], json_body=body, auth=False)
        client.request(method, path, expected_status=[404, 405], json_body=body, invalid_token=True)


def assert_duplicate_and_rollback(config: TestConfig, run_id: str) -> List[tuple[str, Optional[int]]]:
    print("[5/9] Duplicate registration and create-customer rollback checks...")
    dup_username = f"{config.username_prefix}_{run_id}_dup@example.test".lower()
    client = EstoreClient(config.base_url, config.timeout, "duplicate")
    body = make_customer_body(dup_username, config.password, "Dup")
    created_dup = client.create_customer(body, expected_status=201)
    dup_customer_id = created_dup.get("id") if isinstance(created_dup, dict) else None
    client.create_customer(body, expected_status=409)

    rollback_username = f"{config.username_prefix}_{run_id}_rollback@example.test".lower()
    bad_body = make_customer_body(rollback_username, config.password, "Rollback")
    bad_body.pop("first_name")
    client.create_customer(bad_body, expected_status=400)
    client.login(rollback_username, config.password, expected_status=[400, 401])
    return [(dup_username, dup_customer_id if isinstance(dup_customer_id, int) else None), (rollback_username, None)]


def assert_catalog_scope_and_removed_mutations(client: EstoreClient, store: Dict[str, Any], product: Optional[Dict[str, Any]]) -> None:
    print("[6/9] Catalog mismatch checks and direct mutation route removal...")
    store_id = store["id"]
    product_id = product["id"] if product is not None else None

    client.get_store(store_id + 999999, expected_status=[403, 404])
    client.get_products({"store_id": store_id + 999999}, expected_status=403)
    client.get_products({"state": "D"}, expected_status=403)
    client.get_products({"state": "S"}, expected_status=403)
    client.get_products({"state": "R"}, expected_status=403)
    approved = client.get_products({"state": "A"})
    if not isinstance(approved, list) or any(
        not isinstance(row, dict) or row.get("state") != "A" or "review_notes" in row
        for row in approved
    ):
        raise AssertionError(f"Approved-only product filter returned invalid rows: {approved!r}")
    missing_product_id = (product_id + 999999) if isinstance(product_id, int) else 999999999
    client.get_product(missing_product_id, expected_status=[403, 404])
    client.get_inventories(missing_product_id, expected_status=[403, 404])
    client.assert_order_mutation_routes_unavailable()


def assert_read_only_order_payment_endpoints(client: EstoreClient) -> None:
    print("[7/9] Read-only order/order-item/payment endpoint behavior...")
    orders = client.get_orders()
    if not isinstance(orders, list):
        raise AssertionError(f"GET /orders expected list, got {orders!r}")
    order_items = client.get_order_items()
    if not isinstance(order_items, list):
        raise AssertionError(f"GET /order_items expected list, got {order_items!r}")
    for row in order_items:
        if not isinstance(row, dict) or "state" not in row:
            raise AssertionError(f"GET /order_items omitted delivery state: {row!r}")
    payments = client.get_payments()
    if not isinstance(payments, list):
        raise AssertionError(f"GET /payments expected list, got {payments!r}")

    client.get_order(999999999, expected_status=404)
    client.get_order_item(999999999, expected_status=404)
    client.get_payment(999999999, expected_status=404)
    client.request("POST", "/payment", expected_status=[404, 405], json_body={"order_id": 999999999, "currency": "CAD", "amount": 1, "status": "S"})


def assert_cross_customer_denials_without_seeded_orders(customer_a: EstoreClient, customer_b: EstoreClient) -> None:
    print("[8/9] Cross-customer profile and collection isolation checks...")
    profile_a = customer_a.read_customer()
    profile_b = customer_b.read_customer()
    if profile_a.get("id") == profile_b.get("id"):
        raise AssertionError("Two customers resolved to the same profile")

    customer_a.update_customer({"id": profile_b["id"], "first_name": "Bad"}, expected_status=403)
    customer_b.update_customer({"id": profile_a["id"], "first_name": "Bad"}, expected_status=403)

    # With newly created customers and no checkout flow in this test, each collection should be readable.
    for label, rows in [
        ("customer A orders", customer_a.get_orders()),
        ("customer B orders", customer_b.get_orders()),
        ("customer A order_items", customer_a.get_order_items()),
        ("customer B order_items", customer_b.get_order_items()),
        ("customer A payments", customer_a.get_payments()),
        ("customer B payments", customer_b.get_payments()),
    ]:
        if not isinstance(rows, list):
            raise AssertionError(f"{label} expected list, got {rows!r}")


def assert_password_update_security(customer_a: EstoreClient, customer_b: EstoreClient, username_a: str, old_password: str, run_id: str) -> str:
    print("[9/9] Password update security and login behavior...")
    new_password = f"{old_password}-changed-{run_id}!"

    customer_a.update_password({
        "keycloak_user_id": customer_b.keycloak_user_id,
        "current_password": old_password,
        "new_password": new_password,
    }, expected_status=400)
    customer_a.update_password({
        "username": customer_b.username,
        "current_password": old_password,
        "new_password": new_password,
    }, expected_status=400)
    customer_a.update_password({
        "current_password": "definitely-wrong-password",
        "new_password": new_password,
    }, expected_status=403)
    customer_a.update_password({
        "current_password": old_password,
        "new_password": new_password,
    }, expected_status=200)

    customer_a.login(username_a, old_password, expected_status=[400, 401])
    customer_a.login(username_a, new_password, expected_status=200)
    return new_password


def run_suite(config: TestConfig) -> None:
    run_id = uuid.uuid4().hex[:12]
    customer_a = EstoreClient(config.base_url, config.timeout, "customer-A")
    customer_b = EstoreClient(config.base_url, config.timeout, "customer-B")

    username_a = f"{config.username_prefix}_{run_id}_a@example.test".lower()
    username_b = f"{config.username_prefix}_{run_id}_b@example.test".lower()
    cleanup_customers: List[tuple[str, Optional[int]]] = [(username_a, None), (username_b, None)]

    try:
        print("[1/9] Health, configured store, catalogue, and inventory scope...")
        health = customer_a.health()
        if health.get("status") != "ok":
            raise AssertionError(f"Unexpected health payload: {health!r}")
        store = customer_a.get_store()
        if not isinstance(store.get("id"), int):
            raise AssertionError(f"Configured store is not readable: {store!r}")
        product = first_seed_product(customer_a)
        if product is not None:
            inventory = customer_a.get_inventories(product["id"])
            if not isinstance(inventory, list):
                raise AssertionError(f"Inventory payload is not a list: {inventory!r}")
        else:
            print("  catalog is empty; continuing with scope and authentication checks")

        print("[2/9] Create two customers and verify self-scoped profile updates...")
        customer_a.create_customer(make_customer_body(username_a, config.password, "A"), expected_status=201)
        customer_b.create_customer(make_customer_body(username_b, config.password, "B"), expected_status=201)
        cleanup_customers[0] = (username_a, customer_a.customer_id)
        cleanup_customers[1] = (username_b, customer_b.customer_id)
        customer_a.login(username_a, config.password)
        customer_b.login(username_b, config.password)

        profile_a = customer_a.read_customer()
        profile_b = customer_b.read_customer()
        if profile_a.get("id") == profile_b.get("id"):
            raise AssertionError("Two different customer logins resolved to the same BCustomers row")
        if profile_a.get("username") != customer_a.keycloak_user_id:
            raise AssertionError("Customer A BCustomers.username does not match Keycloak user id")
        if profile_b.get("username") != customer_b.keycloak_user_id:
            raise AssertionError("Customer B BCustomers.username does not match Keycloak user id")

        customer_a.update_customer({"id": profile_a["id"], "first_name": "ScopeA", "email": username_a, "phone": "14165550001"})
        updated_a = customer_a.read_customer()
        if updated_a.get("first_name") != "ScopeA" or updated_a.get("phone") != "14165550001":
            raise AssertionError(f"Customer A profile update failed: {updated_a!r}")
        customer_a.update_customer({"id": profile_b["id"], "first_name": "Bad"}, expected_status=403)
        customer_a.update_customer({"id": profile_a["id"], "username": customer_b.keycloak_user_id, "first_name": "Bad"}, expected_status=400)
        customer_a.update_customer({"id": profile_a["id"], "merchant_id": 999999, "first_name": "Bad"}, expected_status=400)

        print("[3/9] Verify direct customer order/order-item mutations are unavailable...")
        customer_a.assert_order_mutation_routes_unavailable()
        customer_b.assert_order_mutation_routes_unavailable()

        assert_missing_and_invalid_tokens(customer_a)
        cleanup_customers.extend(assert_duplicate_and_rollback(config, run_id))
        assert_catalog_scope_and_removed_mutations(customer_a, store, product)
        assert_read_only_order_payment_endpoints(customer_a)
        assert_cross_customer_denials_without_seeded_orders(customer_a, customer_b)
        assert_password_update_security(customer_a, customer_b, username_a, config.password, run_id)

        print("\nPASS: estore-app negative/edge coverage checks passed.")
    finally:
        for username, customer_id in cleanup_customers:
            cleanup_estore_test_customer(username, customer_id, config.timeout, label="test2 cleanup")


if __name__ == "__main__":
    try:
        run_suite(load_config_from_env())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise
