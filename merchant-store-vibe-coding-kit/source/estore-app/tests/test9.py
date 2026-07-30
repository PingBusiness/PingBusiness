#!/usr/bin/env python3
"""Regression test for one-time PaymentAsia popup checkout completion.

Covers:
1. Merchant-controlled network discovery and validation.
2. Backward-compatible HTML checkout launch.
3. Structured JSON popup launch with a stable checkout ID/reference.
4. Authenticated status polling preserves the reference while processing.
5. Empty and malformed browser returns always render visible HTML instead of
   leaking callback-verification errors into a blank checkout window.
6. The notify endpoint remains strict and authoritative.
7. Checkout start still creates no order before verified payment.

The test creates and removes its own approved product, inventory, customer, and
checkout intents. It does not change the merchant's production configuration.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

import requests

from estore_review_test_utils import ApprovedProductFixture
from estore_test_cleanup import cleanup_estore_test_customer
from estore_test_config import biz_admin_credentials, biz_base_url, estore_base_url, first_env, load_test_env


load_test_env()
ExpectedStatus = Union[int, Sequence[int]]
VALID_NETWORKS = {"Alipay", "Wechat", "CUP", "CreditCard", "Fps", "Octopus", "PayMe"}


@dataclass
class Config:
    estore_url: str
    biz_url: str
    admin_username: str
    admin_password: str
    timeout: int
    customer_password: str


def load_config() -> Config:
    username, password = biz_admin_credentials(required=True)
    try:
        timeout = int(first_env("ESTORE_APP_TIMEOUT", default="20") or "20")
    except ValueError as exc:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be an integer") from exc
    if timeout < 1:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be >= 1")
    return Config(
        estore_url=estore_base_url(),
        biz_url=biz_base_url(),
        admin_username=str(username),
        admin_password=str(password),
        timeout=timeout,
        customer_password=first_env("ESTORE_TEST_PASSWORD", default="TestPassword123!") or "TestPassword123!",
    )


@dataclass
class Result:
    status: int
    payload: Any
    text: str


class EstoreClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.token: Optional[str] = None

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: ExpectedStatus,
        body: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Result:
        expected = [expected_status] if isinstance(expected_status, int) else list(expected_status)
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.token:
                raise RuntimeError("Authenticated request attempted before login")
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.session.request(
            method,
            f"{self.config.estore_url}{path}",
            headers=headers,
            json=body,
            timeout=self.config.timeout,
        )
        try:
            payload: Any = response.json() if response.text else None
        except ValueError:
            payload = response.text
        if response.status_code not in expected:
            raise AssertionError(
                f"{method} {path} expected {expected}, got {response.status_code}: "
                f"{json.dumps(payload, default=str)}"
            )
        return Result(response.status_code, payload, response.text)

    def login(self, username: str, password: str) -> None:
        result = self.request(
            "POST",
            "/login",
            expected_status=200,
            body={"username": username, "password": password},
            auth=False,
        )
        token = result.payload.get("access_token") if isinstance(result.payload, dict) else None
        if not token:
            raise AssertionError(f"Login response missing access_token: {result.payload!r}")
        self.token = str(token)

    def create_customer(self, username: str) -> int:
        result = self.request(
            "POST",
            "/customer",
            expected_status=201,
            body={
                "username": username,
                "email": username,
                "password": self.config.customer_password,
                "first_name": "Payment",
                "last_name": "Network",
                "details": "estore payment-network integration test",
                "shipping_address": "100 Network Test Road",
                "billing_address": "100 Network Test Road",
                "phone": "14165550123",
            },
            auth=False,
        )
        customer_id = result.payload.get("id") if isinstance(result.payload, dict) else None
        if not isinstance(customer_id, int):
            raise AssertionError(f"Customer creation missing integer id: {result.payload!r}")
        return customer_id

    def networks(self) -> List[str]:
        result = self.request("GET", "/payment_networks", expected_status=200, auth=False)
        payload = result.payload
        networks = payload.get("payment_networks") if isinstance(payload, dict) else None
        if not isinstance(payload, dict) or payload.get("payment_gateway") != "PAYMENT_ASIA" or not isinstance(networks, list) or not networks:
            raise AssertionError(f"Invalid /payment_networks response: {payload!r}")
        if len(networks) != len(set(networks)):
            raise AssertionError(f"Duplicate configured networks: {networks!r}")
        if any(network not in VALID_NETWORKS for network in networks):
            raise AssertionError(f"Unsupported configured network: {networks!r}")
        return networks

    def orders(self) -> List[Dict[str, Any]]:
        result = self.request("GET", "/orders", expected_status=200)
        if not isinstance(result.payload, list):
            raise AssertionError(f"GET /orders returned non-list payload: {result.payload!r}")
        return result.payload


class BizCleanupClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.token: Optional[str] = None

    def headers(self) -> Dict[str, str]:
        if not self.token:
            login = self.session.post(
                f"{self.config.biz_url}/login",
                headers={"Content-Type": "application/json"},
                json={"username": self.config.admin_username, "password": self.config.admin_password},
                timeout=self.config.timeout,
            )
            if login.status_code != 200:
                raise RuntimeError(f"biz login failed: {login.status_code} {login.text}")
            self.token = login.json().get("access_token")
            if not self.token:
                raise RuntimeError("biz login response missing access_token")
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}

    def get_intent(self, identifier: str) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.config.biz_url}/intents",
            headers=self.headers(),
            params={"identifier": identifier},
            timeout=self.config.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"GET /intents failed: {response.status_code} {response.text}")
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise RuntimeError(f"Expected one intent for {identifier}: {rows!r}")
        return rows[0]

    def delete_customer_intents(self, customer_id: int) -> None:
        response = self.session.get(
            f"{self.config.biz_url}/intents",
            headers=self.headers(),
            params={"customer_id": customer_id},
            timeout=self.config.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"GET /intents failed: {response.status_code} {response.text}")
        for row in response.json() or []:
            intent_id = row.get("id") if isinstance(row, dict) else None
            if not isinstance(intent_id, int):
                continue
            deleted = self.session.delete(
                f"{self.config.biz_url}/intent/{intent_id}",
                headers=self.headers(),
                timeout=self.config.timeout,
            )
            if deleted.status_code not in (200, 404):
                raise RuntimeError(f"DELETE /intent/{intent_id} failed: {deleted.status_code} {deleted.text}")


def parse_json_object(raw: Any, field: str) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError) as exc:
        raise AssertionError(f"{field} is not valid JSON: {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f"{field} is not a JSON object: {raw!r}")
    return parsed


def error_text(result: Result) -> str:
    if isinstance(result.payload, dict):
        return str(result.payload.get("error") or result.payload.get("message") or "")
    return str(result.payload or "")


def extract_hidden_value(document: str, name: str) -> Optional[str]:
    escaped_name = re.escape(name)
    patterns = (
        rf'<input[^>]+name=["\']{escaped_name}["\'][^>]+value=["\']([^"\']+)["\']',
        rf'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']{escaped_name}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, document, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
    return None


def extract_body_attribute(document: str, attribute: str) -> Optional[str]:
    match = re.search(
        rf'<body[^>]+{re.escape(attribute)}=["\']([^"\']+)["\']',
        document,
        flags=re.IGNORECASE,
    )
    return html.unescape(match.group(1)) if match else None


def checkout_body(product_id: int, network: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "cart": [{"product_id": product_id, "quantity": 1}],
        "customer_state": "HK",
        "customer_country": "HK",
        "customer_postal_code": "000000",
    }
    if network is not None:
        body["network"] = network
    return body


def main() -> int:
    config = load_config()
    client = EstoreClient(config)
    cleanup = BizCleanupClient(config)
    fixture: Optional[ApprovedProductFixture] = None
    customer_id: Optional[int] = None
    username = f"auto.estore.network.{uuid.uuid4().hex[:12]}@example.test"

    try:
        print("[1/12] Read and validate configured merchant payment networks...")
        networks = client.networks()
        selected = networks[0]
        if "UserDefine" in networks:
            raise AssertionError(f"UserDefine must not be exposed as a merchant payment method: {networks!r}")

        print("[2/12] Create approved product, inventory, and test customer...")
        fixture = ApprovedProductFixture.create(config.estore_url, config.timeout, quantity=3)
        customer_id = client.create_customer(username)
        client.login(username, config.customer_password)
        before_order_ids = {
            row["id"] for row in client.orders()
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }

        print("[3/12] Checkout rejects a missing network...")
        missing = client.request("POST", "/checkout", expected_status=400, body=checkout_body(fixture.product_id))
        if "network" not in error_text(missing).lower():
            raise AssertionError(f"Unexpected missing-network response: {missing.payload!r}")

        disabled_documented = next((value for value in sorted(VALID_NETWORKS) if value not in networks), None)
        disallowed_network = disabled_documented or "UserDefine"
        print(f"[4/12] Checkout rejects non-enabled network {disallowed_network}...")
        disallowed = client.request(
            "POST",
            "/checkout",
            expected_status=403,
            body=checkout_body(fixture.product_id, disallowed_network),
        )
        if "not enabled" not in error_text(disallowed).lower():
            raise AssertionError(f"Unexpected disallowed-network response: {disallowed.payload!r}")

        print("[5/12] Default checkout remains backward-compatible hosted-payment HTML...")
        html_checkout = client.request(
            "POST",
            "/checkout",
            expected_status=200,
            body=checkout_body(fixture.product_id, selected),
        )
        if "<form" not in html_checkout.text.lower() or "merchant_reference" not in html_checkout.text:
            raise AssertionError("Default checkout did not return the PaymentAsia auto-submit form")
        if extract_hidden_value(html_checkout.text, "network") != selected:
            raise AssertionError("Default checkout form did not preserve the selected network")
        if not re.search(r'name=["\']sign["\']', html_checkout.text, flags=re.IGNORECASE):
            raise AssertionError("Default PaymentAsia hosted form is missing the signature field")

        print("[6/12] JSON popup mode returns structured launch data without HTML parsing...")
        popup_body = checkout_body(fixture.product_id, selected)
        popup_body["response_mode"] = "json"
        popup_checkout = client.request("POST", "/checkout", expected_status=200, body=popup_body)
        launch = popup_checkout.payload
        if not isinstance(launch, dict):
            raise AssertionError(f"Popup checkout returned non-object payload: {launch!r}")
        checkout_id = str(launch.get("checkout_id") or "").strip()
        checkout_reference = str(launch.get("checkout_reference") or "").strip()
        action_url = str(launch.get("action_url") or "").strip()
        fields = launch.get("fields")
        if not checkout_id or not checkout_reference:
            raise AssertionError(f"Popup launch is missing checkout identity: {launch!r}")
        if not action_url.startswith(("https://", "http://")):
            raise AssertionError(f"Popup launch has invalid action_url: {action_url!r}")
        if not isinstance(fields, dict) or not fields:
            raise AssertionError(f"Popup launch has invalid signed fields: {launch!r}")
        if str(fields.get("network") or "") != selected:
            raise AssertionError(f"Popup launch network expected {selected!r}, got {fields.get('network')!r}")
        if not fields.get("sign"):
            raise AssertionError("Popup launch is missing the PaymentAsia signature field")
        if str(fields.get("merchant_reference") or "") != checkout_reference:
            raise AssertionError("Popup checkout_reference does not match the signed merchant_reference")

        stored_intent = cleanup.get_intent(checkout_id)
        immutable_input = parse_json_object(stored_intent.get("intent_details"), "intent_details")
        trusted_state = parse_json_object(stored_intent.get("system_details"), "system_details")
        if immutable_input.get("source") != "estore_checkout" or not isinstance(immutable_input.get("line_items"), list):
            raise AssertionError(f"Checkout intent_details missing storefront cart snapshot: {stored_intent!r}")
        if "checkout_approval" in immutable_input:
            raise AssertionError("Trusted checkout approval leaked into ESTORE-owned intent_details")
        approval = trusted_state.get("checkout_approval")
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            raise AssertionError(f"Trusted system_details missing checkout approval: {stored_intent!r}")
        original_intent_details_raw = stored_intent.get("intent_details")

        print("[7/12] Processing status preserves the checkout reference and remains non-terminal...")
        pending = client.request("GET", f"/checkout/status/{checkout_id}", expected_status=200)
        if not isinstance(pending.payload, dict):
            raise AssertionError(f"Checkout status returned invalid payload: {pending.payload!r}")
        if pending.payload.get("complete") is not False or pending.payload.get("status") not in {"C", "R"}:
            raise AssertionError(f"New checkout should remain non-terminal: {pending.payload!r}")
        if pending.payload.get("checkout_reference") != checkout_reference:
            raise AssertionError(f"Checkout status lost checkout_reference: {pending.payload!r}")
        if pending.payload.get("payment_reference") != checkout_reference:
            raise AssertionError(f"Checkout status lost its provisional payment reference: {pending.payload!r}")

        print("[8/12] Empty browser return always renders visible processing HTML...")
        empty_return = client.request(
            "GET",
            f"/checkout/return/{checkout_id}",
            expected_status=202,
            auth=False,
        )
        lower_empty = empty_return.text.lower()
        if "<!doctype html" not in lower_empty or "waiting for the secure payment confirmation" not in lower_empty:
            raise AssertionError(f"Empty browser return was not a visible processing page: {empty_return.text[:500]!r}")
        if f'data-checkout-id="{checkout_id}"' not in empty_return.text:
            raise AssertionError("Empty browser return did not preserve the checkout ID")

        print("[9/12] Malformed signed browser return also falls back to visible HTML...")
        malformed_callback = {
            "amount": str(fields.get("amount") or "0.00"),
            "currency": str(fields.get("currency") or "HKD"),
            "merchant_reference": checkout_reference,
            "request_reference": "INVALID_BROWSER_RETURN_REFERENCE",
            "status": "Success",
            "original_merchant_reference": checkout_reference,
            "payment_type": "Sale",
            "network": str(fields.get("network") or selected),
            "sign": "definitely-not-a-valid-paymentasia-signature",
        }
        malformed_return = client.request(
            "POST",
            f"/checkout/return/{checkout_id}",
            expected_status=202,
            body=malformed_callback,
            auth=False,
        )
        lower_malformed = malformed_return.text.lower()
        if "<!doctype html" not in lower_malformed or "checkout processing" not in lower_malformed:
            raise AssertionError(
                "Malformed browser return leaked a callback error instead of HTML: "
                f"{malformed_return.text[:500]!r}"
            )
        if '{"error"' in lower_malformed or "invalid signature" in lower_malformed:
            raise AssertionError("Malformed browser return exposed verifier error JSON/text")

        print("[10/12] Browser-return fallback does not mutate the pending checkout...")
        after_return = client.request("GET", f"/checkout/status/{checkout_id}", expected_status=200)
        if not isinstance(after_return.payload, dict) or after_return.payload.get("complete") is not False:
            raise AssertionError(f"Browser-return fallback changed checkout state: {after_return.payload!r}")
        if after_return.payload.get("payment_reference") != checkout_reference:
            raise AssertionError(f"Browser-return fallback lost the checkout reference: {after_return.payload!r}")
        after_return_intent = cleanup.get_intent(checkout_id)
        if after_return_intent.get("intent_details") != original_intent_details_raw:
            raise AssertionError("Untrusted callback path changed immutable intent_details")
        after_return_system = parse_json_object(after_return_intent.get("system_details"), "system_details")
        if not isinstance(after_return_system.get("checkout_approval"), dict):
            raise AssertionError("Trusted checkout approval disappeared from system_details")

        print("[11/12] Notify remains strict and rejects the same malformed callback...")
        strict_notify = client.request(
            "POST",
            f"/checkout/notify/{checkout_id}",
            expected_status=(400, 502),
            body=malformed_callback,
            auth=False,
        )
        if strict_notify.status < 400:
            raise AssertionError(f"Malformed notify was unexpectedly accepted: {strict_notify.payload!r}")

        print("[12/12] Checkout start did not create an order before verified payment...")
        after_order_ids = {
            row["id"] for row in client.orders()
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }
        if after_order_ids != before_order_ids:
            raise AssertionError(f"Checkout start unexpectedly changed customer orders: {after_order_ids - before_order_ids!r}")

        print("\nPASS: one-time popup launch, browser-return fallback, strict notify, and reference preservation verified.")
        return 0
    finally:
        errors: List[str] = []
        if customer_id is not None:
            try:
                cleanup.delete_customer_intents(customer_id)
            except Exception as exc:
                errors.append(f"intent cleanup: {exc}")
        try:
            cleanup_estore_test_customer(
                username,
                customer_id,
                config.timeout,
                label="test9 cleanup",
                require_biz_cleanup=customer_id is not None,
            )
        except Exception as exc:
            errors.append(f"customer cleanup: {exc}")
        if fixture is not None:
            try:
                fixture.cleanup()
            except Exception as exc:
                errors.append(f"fixture cleanup: {exc}")
        if errors:
            raise AssertionError("Cleanup failed: " + "; ".join(errors))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
