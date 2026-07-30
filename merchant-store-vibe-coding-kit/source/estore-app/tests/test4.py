#!/usr/bin/env python3
"""Checkout inventory guard integration test for estore-app.

The test creates its own temporary Approved product with inventory and a
temporary eStore customer. It then tries to buy one more unit than is available.
The expected result is HTTP 400 before any order, intent, or payment is created.

Cleanup removes the temporary product, manager, customer row, and ESTORE
Keycloak user. Cleanup failures fail the test.
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

from estore_test_config import biz_admin_credentials, biz_base_url, estore_base_url, load_test_env

from estore_review_test_utils import ApprovedProductFixture
from estore_test_cleanup import cleanup_estore_test_customer

load_test_env()
ExpectedStatus = Union[int, List[int]]


@dataclass
class TestConfig:
    base_url: str
    timeout: int
    username_prefix: str
    password: str
    biz_base_url: str
    biz_admin_username: Optional[str]
    biz_admin_password: Optional[str]


@dataclass
class ResponseResult:
    status_code: int
    payload: Any


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


def load_config_from_env() -> TestConfig:
    try:
        timeout = int(env("ESTORE_APP_TIMEOUT", "20") or "20")
    except ValueError as exc:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be an integer") from exc
    if timeout < 1:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be >= 1")

    return TestConfig(
        base_url=estore_base_url(),
        timeout=timeout,
        username_prefix=env("ESTORE_TEST_USERNAME_PREFIX", "AUTO_ESTORE_INV") or "AUTO_ESTORE_INV",
        password=env("ESTORE_TEST_PASSWORD", "TestPassword123!") or "TestPassword123!",
        biz_base_url=biz_base_url(),
        biz_admin_username=biz_admin_credentials(required=False)[0],
        biz_admin_password=biz_admin_credentials(required=False)[1],
    )


class EstoreClient:
    def __init__(self, base_url: str, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def headers(self, *, auth: bool = True) -> Dict[str, str]:
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

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: ExpectedStatus,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Any:
        return self.request_result(
            method,
            path,
            expected_status=expected_status,
            json_body=json_body,
            params=params,
            auth=auth,
        ).payload

    def health(self) -> Any:
        return self.request("GET", "/health", expected_status=200, auth=False)

    def create_customer(self, body: Dict[str, Any]) -> Any:
        return self.request("POST", "/customer", expected_status=201, json_body=body, auth=False)

    def login(self, username: str, password: str) -> Any:
        payload = self.request(
            "POST",
            "/login",
            expected_status=200,
            json_body={"username": username, "password": password},
            auth=False,
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"Login did not return access_token: {payload!r}")
        self.access_token = token
        return payload

    def get_products(self) -> List[Dict[str, Any]]:
        payload = self.request("GET", "/products", expected_status=200, auth=False)
        if not isinstance(payload, list):
            raise AssertionError(f"GET /products returned non-list payload: {payload!r}")
        return payload

    def get_product(self, product_id: int) -> Dict[str, Any]:
        payload = self.request(
            "GET",
            f"/product/{product_id}",
            expected_status=200,
            auth=False,
        )
        if not isinstance(payload, dict):
            raise AssertionError(f"GET /product/{product_id} returned non-object payload: {payload!r}")
        return payload

    def get_inventories(self, product_id: int) -> List[Dict[str, Any]]:
        payload = self.request(
            "GET",
            "/inventories",
            expected_status=200,
            params={"product_id": product_id},
            auth=False,
        )
        if not isinstance(payload, list):
            raise AssertionError(f"GET /inventories returned non-list payload: {payload!r}")
        return payload

    def get_orders(self) -> List[Dict[str, Any]]:
        payload = self.request("GET", "/orders", expected_status=200)
        if not isinstance(payload, list):
            raise AssertionError(f"GET /orders returned non-list payload: {payload!r}")
        return payload

    def get_payment_networks(self) -> List[str]:
        payload = self.request("GET", "/payment_networks", expected_status=200, auth=False)
        networks = payload.get("payment_networks") if isinstance(payload, dict) else None
        if not isinstance(networks, list) or not networks or not all(isinstance(value, str) and value for value in networks):
            raise AssertionError(f"GET /payment_networks returned invalid payload: {payload!r}")
        return networks

    def checkout(self, body: Dict[str, Any], expected_status: ExpectedStatus) -> ResponseResult:
        return self.request_result("POST", "/checkout", expected_status=expected_status, json_body=body)


class BizCleanupClient:
    def __init__(self, config: TestConfig) -> None:
        self.base_url = config.biz_base_url.rstrip("/")
        self.timeout = config.timeout
        self.username = config.biz_admin_username
        self.password = config.biz_admin_password
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def headers(self, *, auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.access_token:
                raise RuntimeError("Biz cleanup request attempted before login")
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request(self, method: str, path: str, *, expected_status: ExpectedStatus, json_body: Optional[Dict[str, Any]] = None) -> Any:
        expected = expected_status if isinstance(expected_status, list) else [expected_status]
        response = self.session.request(
            method=method,
            url=self.url(path),
            headers=self.headers(auth=path != "/login"),
            json=json_body,
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
            raise RuntimeError(f"biz {method} {path} expected {expected}, got {response.status_code}: {payload!r}")
        return payload

    def login(self) -> None:
        if not self.configured:
            raise RuntimeError("Biz cleanup is not configured")
        payload = self.request(
            "POST",
            "/login",
            expected_status=200,
            json_body={"username": self.username, "password": self.password},
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise RuntimeError(f"biz /login missing access_token: {payload!r}")
        self.access_token = token

    def delete_customer(self, customer_id: Optional[int]) -> bool:
        if not customer_id or not self.configured:
            return False
        if not self.access_token:
            self.login()
        self.request("DELETE", f"/customer/{customer_id}", expected_status=[200, 204, 404])
        return True


def make_customer_body(username: str, password: str) -> Dict[str, Any]:
    return {
        "username": username,
        "email": username,
        "password": password,
        "first_name": "Inventory",
        "last_name": "Guard",
        "details": "checkout inventory guard test customer",
        "shipping_address": "100 Inventory Guard Road",
        "billing_address": "200 Inventory Guard Road",
        "phone": "14165550123",
    }


def cleanup_created_data(config: TestConfig, username: str, customer_id: Optional[int]) -> None:
    cleanup_estore_test_customer(
        username,
        customer_id,
        config.timeout,
        label="test4 cleanup",
        require_biz_cleanup=True,
    )


def run_suite(config: TestConfig) -> None:
    client = EstoreClient(config.base_url, config.timeout)
    run_id = uuid.uuid4().hex[:12]
    username = f"{config.username_prefix}_{run_id}@example.test".lower()
    customer_id: Optional[int] = None
    fixture: Optional[ApprovedProductFixture] = None

    try:
        print("[1/5] Health and create a temporary approved product fixture...")
        health = client.health()
        if health.get("status") != "ok":
            raise AssertionError(f"Unexpected health payload: {health!r}")
        fixture = ApprovedProductFixture.create(config.base_url, config.timeout, quantity=3)

        print("[2/5] Create temporary customer and read current inventory...")
        created = client.create_customer(make_customer_body(username, config.password))
        customer_id = created.get("id") if isinstance(created, dict) else None
        if not isinstance(customer_id, int):
            raise AssertionError(f"POST /customer missing integer id: {created!r}")
        client.login(username, config.password)
        product_id = fixture.product_id
        product = client.get_product(product_id)
        available = sum(int(row.get("quantity") or 0) for row in client.get_inventories(product_id) if isinstance(row, dict))
        requested = available + 1
        print(f"  product {product_id}: available={available}, requested={requested}")

        print("[3/5] Confirm no orders exist for the new customer before checkout...")
        before_orders = client.get_orders()
        if before_orders:
            raise AssertionError(f"New test customer unexpectedly has orders before checkout: {before_orders!r}")

        print("[4/5] Attempt over-inventory checkout and expect HTTP 400...")
        payment_network = client.get_payment_networks()[0]
        result = client.checkout(
            {
                "network": payment_network,
                "cart": [{"product_id": product_id, "quantity": requested}],
                "customer_state": "HK",
                "customer_country": "HK",
                "customer_postal_code": "000000",
            },
            expected_status=400,
        )
        error_text = ""
        if isinstance(result.payload, dict):
            error_text = str(result.payload.get("error") or result.payload.get("message") or "")
        else:
            error_text = str(result.payload or "")
        if "insufficient inventory" not in error_text.lower() or str(product_id) not in error_text:
            raise AssertionError(f"Unexpected checkout error payload: {result.payload!r}")

        print("[5/5] Verify blocked checkout did not create orders...")
        after_orders = client.get_orders()
        if after_orders:
            raise AssertionError(f"Blocked checkout created orders: {after_orders!r}")

        print("\nPASS: estore-app checkout inventory guard rejected over-available quantity without creating orders.")
    finally:
        cleanup_errors: List[str] = []
        try:
            cleanup_created_data(config, username, customer_id)
        except Exception as exc:
            cleanup_errors.append(f"customer cleanup: {exc}")
        if fixture is not None:
            try:
                fixture.cleanup()
            except Exception as exc:
                cleanup_errors.append(f"product fixture cleanup: {exc}")
        if cleanup_errors:
            raise AssertionError("Cleanup failed: " + "; ".join(cleanup_errors))


if __name__ == "__main__":
    try:
        run_suite(load_config_from_env())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise
