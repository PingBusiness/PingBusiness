#!/usr/bin/env python3
"""Estore checkout smoke test for the biz-app-bound PaymentAsia proxy.

The old version of this test called biz-app /pa/checkout directly. That endpoint
now requires an existing store-scoped intent/order, so this test exercises the
real merchant deployment path instead:

  estore-app /checkout
    -> creates an order-less checkout intent through biz-app
    -> calls biz-app /pa/checkout with intent_identifier
    -> receives signed hosted-payment fields

Idempotence:
  The test creates its own temporary Approved product with inventory, manager,
  eStore customer, and checkout intent. Orders are not created at checkout
  start. Cleanup removes all temporary objects and fails the test if incomplete.
"""

from __future__ import annotations

import json
import os
import re
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
    estore_base_url: str
    biz_base_url: str
    biz_admin_username: str
    biz_admin_password: str
    timeout: int
    username_prefix: str
    password: str


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


def env_with_fallback(primary: str, fallback: str) -> str:
    value = env(primary)
    return value if value else require_env(fallback)


def load_config_from_env() -> TestConfig:
    timeout = int(env("ESTORE_APP_TIMEOUT", "20") or "20")
    if timeout < 1:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be >= 1")
    return TestConfig(
        estore_base_url=estore_base_url(),
        biz_base_url=biz_base_url(),
        biz_admin_username=biz_admin_credentials(required=True)[0] or "",
        biz_admin_password=biz_admin_credentials(required=True)[1] or "",
        timeout=timeout,
        username_prefix=env("ESTORE_TEST_USERNAME_PREFIX", "AUTO_ESTORE_CHECKOUT_PROXY") or "AUTO_ESTORE_CHECKOUT_PROXY",
        password=env("ESTORE_TEST_PASSWORD", "TestPassword123!") or "TestPassword123!",
    )


class EstoreClient:
    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    def headers(self, auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.access_token:
                raise RuntimeError("Authenticated request attempted before login")
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request_result(self, method: str, path: str, *, expected_status: ExpectedStatus, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, auth: bool = True) -> Any:
        expected = expected_status if isinstance(expected_status, list) else [expected_status]
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=self.headers(auth=auth),
            json=json_body,
            params=params,
            timeout=self.timeout,
        )
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload: Any = response.json()
        else:
            payload = response.text
        if response.status_code not in expected:
            raise AssertionError(f"{method} {path} expected {expected}, got {response.status_code}: {json.dumps(payload, default=str)}")
        return payload

    def health(self) -> Any:
        return self.request_result("GET", "/health", expected_status=200, auth=False)

    def create_customer(self, body: Dict[str, Any]) -> Any:
        return self.request_result("POST", "/customer", expected_status=201, json_body=body, auth=False)

    def login(self, username: str, password: str) -> None:
        payload = self.request_result("POST", "/login", expected_status=200, json_body={"username": username, "password": password}, auth=False)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"Login did not return access_token: {payload!r}")
        self.access_token = token

    def get_products(self) -> List[Dict[str, Any]]:
        payload = self.request_result("GET", "/products", expected_status=200, auth=False)
        if not isinstance(payload, list):
            raise AssertionError(f"GET /products returned non-list payload: {payload!r}")
        return payload

    def get_inventories(self, product_id: int) -> List[Dict[str, Any]]:
        payload = self.request_result("GET", "/inventories", expected_status=200, params={"product_id": product_id}, auth=False)
        if not isinstance(payload, list):
            raise AssertionError(f"GET /inventories returned non-list payload: {payload!r}")
        return payload

    def get_orders(self) -> List[Dict[str, Any]]:
        payload = self.request_result("GET", "/orders", expected_status=200)
        if not isinstance(payload, list):
            raise AssertionError(f"GET /orders returned non-list payload: {payload!r}")
        return payload

    def get_payment_networks(self) -> List[str]:
        payload = self.request_result("GET", "/payment_networks", expected_status=200, auth=False)
        networks = payload.get("payment_networks") if isinstance(payload, dict) else None
        if not isinstance(networks, list) or not networks or not all(isinstance(value, str) and value for value in networks):
            raise AssertionError(f"GET /payment_networks returned invalid payload: {payload!r}")
        return networks

    def checkout(self, product_id: int) -> str:
        return self.request_result(
            "POST",
            "/checkout",
            expected_status=200,
            json_body={
                "network": self.get_payment_networks()[0],
                "cart": [{"product_id": product_id, "quantity": 1}],
                "customer_state": "HK",
                "customer_country": "HK",
                "customer_postal_code": "000000",
            },
        )


class BizCleanupClient:
    def __init__(self, cfg: TestConfig):
        self.base_url = cfg.biz_base_url.rstrip("/")
        self.timeout = cfg.timeout
        self.username = cfg.biz_admin_username
        self.password = cfg.biz_admin_password
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    def headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise RuntimeError("Biz cleanup request attempted before login")
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"}

    def login(self) -> None:
        response = self.session.post(
            f"{self.base_url}/login",
            headers={"Content-Type": "application/json"},
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"biz /login failed during cleanup: {response.status_code} {response.text}")
        self.access_token = response.json().get("access_token")
        if not self.access_token:
            raise RuntimeError("biz /login missing access_token during cleanup")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.access_token:
            self.login()
        response = self.session.get(f"{self.base_url}{path}", headers=self.headers(), params=params, timeout=self.timeout)
        if response.status_code != 200:
            raise RuntimeError(f"GET {path} expected 200, got {response.status_code}: {response.text}")
        return response.json()

    def delete(self, path: str) -> None:
        if not self.access_token:
            self.login()
        response = self.session.delete(f"{self.base_url}{path}", headers=self.headers(), timeout=self.timeout)
        if response.status_code not in (200, 404):
            raise RuntimeError(f"DELETE {path} expected 200/404, got {response.status_code}: {response.text}")


def make_customer_body(username: str, password: str) -> Dict[str, Any]:
    return {
        "username": username,
        "email": username,
        "password": password,
        "first_name": "Checkout",
        "last_name": "Proxy",
        "details": "checkout pa proxy test customer",
        "shipping_address": "100 Proxy Test Road",
        "billing_address": "200 Proxy Test Road",
        "phone": "14165550123",
    }


def cleanup_created_data(cfg: TestConfig, username: str, customer_id: Optional[int], order_ids: List[int]) -> None:
    errors: List[str] = []
    try:
        biz = BizCleanupClient(cfg)
        if customer_id is not None:
            try:
                intents = biz.get("/intents", params={"customer_id": customer_id})
                if isinstance(intents, list):
                    for intent in intents:
                        intent_id = intent.get("id") if isinstance(intent, dict) else None
                        if isinstance(intent_id, int):
                            try:
                                biz.delete(f"/intent/{intent_id}")
                            except Exception as exc:
                                errors.append(f"intent {intent_id}: {exc}")
            except Exception as exc:
                errors.append(f"intent lookup for customer {customer_id}: {exc}")
        for order_id in reversed(order_ids):
            try:
                biz.delete(f"/order/{order_id}")
            except Exception as exc:
                errors.append(f"order {order_id}: {exc}")
    finally:
        try:
            cleanup_estore_test_customer(username, customer_id, cfg.timeout, label="test5 cleanup", require_biz_cleanup=True)
        except Exception as exc:
            errors.append(f"customer/keycloak cleanup: {exc}")
    if errors:
        raise AssertionError("Cleanup failed: " + "; ".join(errors))


def run_suite(cfg: TestConfig) -> None:
    client = EstoreClient(cfg.estore_base_url, cfg.timeout)
    run_id = uuid.uuid4().hex[:12]
    username = f"{cfg.username_prefix}_{run_id}@example.test".lower()
    customer_id: Optional[int] = None
    created_order_ids: List[int] = []
    fixture: Optional[ApprovedProductFixture] = None

    try:
        health = client.health()
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise AssertionError(f"Unexpected health payload: {health!r}")
        fixture = ApprovedProductFixture.create(cfg.estore_base_url, cfg.timeout, quantity=3)
        product_id = fixture.product_id

        customer = client.create_customer(make_customer_body(username, cfg.password))
        customer_id = customer.get("id") if isinstance(customer, dict) else None
        if not isinstance(customer_id, int):
            raise AssertionError(f"POST /customer missing integer id: {customer!r}")
        client.login(username, cfg.password)
        before_ids = {int(row["id"]) for row in client.get_orders() if isinstance(row, dict) and isinstance(row.get("id"), int)}
        html = client.checkout(product_id)
        if not isinstance(html, str) or "<form" not in html.lower() or "merchant_reference" not in html:
            raise AssertionError("Checkout did not return expected PaymentAsia auto-submit HTML")
        if not re.search(r'name=["\']sign["\']', html, flags=re.IGNORECASE):
            raise AssertionError("Checkout HTML did not include signed PaymentAsia fields")
        after_orders = client.get_orders()
        after_ids = {int(row["id"]) for row in after_orders if isinstance(row, dict) and isinstance(row.get("id"), int)}
        created_order_ids = sorted(after_ids - before_ids)
        if created_order_ids:
            raise AssertionError(f"Checkout start should not create orders before verified payment: {after_orders!r}")
        print("\nPASS: estore-app checkout used order-less biz-app PaymentAsia proxy and returned signed hosted-payment HTML.")
    finally:
        cleanup_errors: List[str] = []
        try:
            cleanup_created_data(cfg, username, customer_id, created_order_ids)
        except Exception as exc:
            cleanup_errors.append(f"customer/intent cleanup: {exc}")
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
        raise SystemExit(1)
