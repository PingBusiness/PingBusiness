#!/usr/bin/env python3
"""End-to-end eStore single-product subscription checkout test.

The storefront contract is deliberately split:

* POST /checkout accepts one-time cart items only.
* POST /subscribe accepts exactly one recurring product and quantity >= 1.

This test verifies both boundary rules and the successful subscription flow. A
a navigation-only PaymentAsia browser return must not be treated as a callback;
the verified tokenization notify must create one recurring schedule,
one successful order, and exactly one recurring order item. No Standard Hosted
Payment step or BPayments row is involved.

Required additional environment:
  PA_SECRET_CODE
  PA_TEST_TOKENIZATION_ID
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Union

import requests

from estore_review_test_utils import (
    ApprovedProductFixture,
    BizReviewClient,
    delete_orders_direct,
)
from estore_test_cleanup import cleanup_estore_test_customer
from estore_test_config import estore_base_url, first_env, load_test_env


load_test_env()
ExpectedStatus = Union[int, Sequence[int]]


@dataclass
class Config:
    estore_url: str
    timeout: int
    customer_password: str
    secret_code: str
    tokenization_id: str


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required .env value: {name}")
    return value.strip()


def load_config() -> Config:
    try:
        timeout = int(first_env("ESTORE_APP_TIMEOUT", default="30") or "30")
    except ValueError as exc:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be an integer") from exc
    if timeout < 1:
        raise RuntimeError("ESTORE_APP_TIMEOUT must be >= 1")
    return Config(
        estore_url=estore_base_url(),
        timeout=timeout,
        customer_password=first_env("ESTORE_TEST_PASSWORD", default="TestPassword123!") or "TestPassword123!",
        secret_code=require_env("PA_SECRET_CODE"),
        tokenization_id=require_env("PA_TEST_TOKENIZATION_ID"),
    )


def paymentasia_sign(fields: Dict[str, Any], secret_code: str) -> str:
    ordered = sorted(
        (key, str(value))
        for key, value in fields.items()
        if key != "sign" and value is not None
    )
    query = urllib.parse.urlencode(
        ordered,
        doseq=False,
        quote_via=urllib.parse.quote_plus,
        safe="",
    )
    return hashlib.sha512((query + secret_code).encode("utf-8")).hexdigest()


def signed_tokenization_payload(reference: str, tokenization_id: str, secret_code: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "merchant_reference": reference,
        "tokenization_id": tokenization_id,
        "status": "Success",
        "card_first6": "411111",
        "card_last4": "1111",
        "card_expiry_month": "12",
        "card_expiry_year": "2030",
    }
    payload["sign"] = paymentasia_sign(payload, secret_code)
    return payload


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
        json_body: Optional[Dict[str, Any]] = None,
        form_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Result:
        expected = {expected_status} if isinstance(expected_status, int) else set(expected_status)
        headers: Dict[str, str] = {}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.token:
                raise RuntimeError("Authenticated eStore request attempted before login")
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.session.request(
            method,
            f"{self.config.estore_url}{path}",
            headers=headers,
            json=json_body,
            data=form_body,
            params=params,
            timeout=self.config.timeout,
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
        return Result(response.status_code, payload, response.text)

    def create_customer(self, username: str) -> int:
        result = self.request(
            "POST",
            "/customer",
            expected_status=201,
            auth=False,
            json_body={
                "username": username,
                "email": username,
                "password": self.config.customer_password,
                "first_name": "Subscription",
                "last_name": "Checkout",
                "details": "temporary single-subscription checkout integration customer",
                "shipping_address": "100 Subscription Test Road",
                "billing_address": "100 Subscription Test Road",
                "phone": "14165550123",
            },
        )
        customer_id = result.payload.get("id") if isinstance(result.payload, dict) else None
        if not isinstance(customer_id, int):
            raise AssertionError(f"Customer creation missing integer id: {result.payload!r}")
        return customer_id

    def login(self, username: str) -> None:
        result = self.request(
            "POST",
            "/login",
            expected_status=200,
            auth=False,
            json_body={"username": username, "password": self.config.customer_password},
        )
        token = result.payload.get("access_token") if isinstance(result.payload, dict) else None
        if not token:
            raise AssertionError(f"Login response missing access_token: {result.payload!r}")
        self.token = str(token)


def parse_intent_field(intent: Dict[str, Any], field: str) -> Dict[str, Any]:
    raw = intent.get(field)
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise AssertionError(f"Intent {field} is not an object: {raw!r}")
    return parsed


def parse_intent_details(intent: Dict[str, Any]) -> Dict[str, Any]:
    return parse_intent_field(intent, "intent_details")


def parse_system_details(intent: Dict[str, Any]) -> Dict[str, Any]:
    return parse_intent_field(intent, "system_details")


def get_one_intent(admin: BizReviewClient, identifier: str) -> Dict[str, Any]:
    rows = admin.request(
        "GET",
        "/intents",
        expected_status=200,
        params={"identifier": identifier},
    )
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise AssertionError(f"Expected one intent for {identifier}: {rows!r}")
    return rows[0]


def customer_intents(admin: BizReviewClient, customer_id: int) -> list[Dict[str, Any]]:
    rows = admin.request(
        "GET",
        "/intents",
        expected_status=200,
        params={"customer_id": customer_id},
    )
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AssertionError(f"Invalid customer intent response: {rows!r}")
    return rows


def inventory_total(client: EstoreClient, product_id: int) -> int:
    result = client.request(
        "GET",
        "/inventories",
        expected_status=200,
        params={"product_id": product_id},
        auth=False,
    )
    if not isinstance(result.payload, list):
        raise AssertionError(f"Inventory response is not a list: {result.payload!r}")
    return sum(int((row or {}).get("quantity") or 0) for row in result.payload if isinstance(row, dict))


def extract_checkout_id(document: str) -> str:
    match = re.search(r'data-checkout-id=["\']([^"\']+)["\']', document, flags=re.IGNORECASE)
    if not match:
        raise AssertionError(f"Subscription redirect page has no checkout ID: {document[:500]!r}")
    return html.unescape(match.group(1))


def assert_error_contains(result: Result, text: str) -> None:
    message = result.payload.get("error") if isinstance(result.payload, dict) else str(result.payload)
    if text.lower() not in str(message).lower():
        raise AssertionError(f"Expected error containing {text!r}, got {result.payload!r}")


def assert_enabled_credit_card(client: EstoreClient) -> None:
    result = client.request("GET", "/payment_networks", expected_status=200, auth=False)
    networks = result.payload.get("payment_networks") if isinstance(result.payload, dict) else None
    if not isinstance(networks, list) or "CreditCard" not in networks:
        raise AssertionError(
            "Subscription checkout requires CreditCard in the configured merchant "
            f"payment networks; current response: {result.payload!r}"
        )


def cancel_recurring_items(admin: BizReviewClient, item_ids: Iterable[int]) -> None:
    for item_id in item_ids:
        current = admin.request("GET", f"/order_item/{item_id}", expected_status=(200, 204))
        if not isinstance(current, dict):
            continue
        if current.get("recurring_status") in {"CANCELLED", "COMPLETED"}:
            continue
        admin.request(
            "POST",
            f"/order_item/{item_id}/recurring/cancel",
            expected_status=(200, 409, 502),
            json_body={},
        )


def main() -> int:
    config = load_config()
    client = EstoreClient(config)
    admin = BizReviewClient(config.timeout)
    ordinary: Optional[ApprovedProductFixture] = None
    recurring: Optional[ApprovedProductFixture] = None
    customer_id: Optional[int] = None
    order_id: Optional[int] = None
    intent_id: Optional[int] = None
    recurring_item_ids: list[int] = []
    username = f"auto.estore.subscription.{uuid.uuid4().hex[:12]}@example.test"

    try:
        print("[1/10] Validate recurring card network and create approved products...")
        assert_enabled_credit_card(client)
        ordinary = ApprovedProductFixture.create(
            config.estore_url,
            config.timeout,
            quantity=4,
            amount="12.34",
        )
        recurring = ApprovedProductFixture.create(
            config.estore_url,
            config.timeout,
            quantity=5,
            amount="5.00",
            recurring_frequency="WEEKLY",
            recurring_intervals=1,
            recurring_total_execution_times=2,
        )
        if ordinary.store_id != recurring.store_id or ordinary.merchant_id != recurring.merchant_id:
            raise AssertionError("Subscription fixtures were not created in the configured eStore scope")

        print("[2/10] Create and authenticate a temporary eStore customer...")
        customer_id = client.create_customer(username)
        client.login(username)
        admin.login_admin()
        if customer_intents(admin, customer_id):
            raise AssertionError("New customer unexpectedly has checkout intents")

        print("[3/10] Enforce cart/subscription separation before creating an intent...")
        recurring_cart = client.request(
            "POST",
            "/checkout",
            expected_status=400,
            json_body={
                "network": "CreditCard",
                "cart": [{"product_id": recurring.product_id, "quantity": 1}],
            },
        )
        assert_error_contains(recurring_cart, "Subscribe Now")

        mixed_cart = client.request(
            "POST",
            "/checkout",
            expected_status=400,
            json_body={
                "network": "CreditCard",
                "cart": [
                    {"product_id": ordinary.product_id, "quantity": 1},
                    {"product_id": recurring.product_id, "quantity": 1},
                ],
            },
        )
        assert_error_contains(mixed_cart, "Subscribe Now")

        ordinary_subscription = client.request(
            "POST",
            "/subscribe",
            expected_status=400,
            json_body={"product_id": ordinary.product_id, "quantity": 1},
        )
        assert_error_contains(ordinary_subscription, "subscription product")
        if customer_intents(admin, customer_id):
            raise AssertionError("Rejected cart/subscription requests created an intent")

        print("[4/10] Start Subscribe Now for one recurring product with quantity two...")
        subscription = client.request(
            "POST",
            "/subscribe",
            expected_status=200,
            json_body={
                "product_id": recurring.product_id,
                "quantity": 2,
                "subject": "Single recurring eStore subscription test",
            },
        )
        if "secure card verification" not in subscription.text.lower():
            raise AssertionError(f"Subscribe Now did not render tokenization redirect: {subscription.text[:500]!r}")
        checkout_id = extract_checkout_id(subscription.text)
        intent = get_one_intent(admin, checkout_id)
        intent_id = int(intent["id"])
        details = parse_intent_details(intent)
        original_intent_details_raw = intent.get("intent_details")
        context = parse_system_details(intent).get("recurring_checkout")
        if details.get("checkout_kind") != "subscription" or details.get("source") != "estore_subscription":
            raise AssertionError(f"Intent is not classified as a subscription: {details!r}")
        if details.get("subscription") != {"product_id": recurring.product_id, "quantity": 2}:
            raise AssertionError(f"Intent subscription selection is incorrect: {details!r}")
        line_items = details.get("line_items")
        if not isinstance(line_items, list) or len(line_items) != 1:
            raise AssertionError(f"Subscription intent must have exactly one line item: {details!r}")
        line = line_items[0]
        if int(line.get("product_id") or 0) != recurring.product_id or int(line.get("quantity") or 0) != 2:
            raise AssertionError(f"Subscription line does not preserve product and quantity: {line!r}")
        if Decimal(str(line.get("amount"))) != Decimal("10.00"):
            raise AssertionError(f"Subscription amount is not unit price x quantity: {line!r}")
        if not isinstance(context, dict) or context.get("state") != "TOKENIZATION_PENDING":
            raise AssertionError(f"Intent did not enter TOKENIZATION_PENDING: {intent!r}")
        tokenization_reference = str(context.get("tokenization_merchant_reference") or "")
        if not tokenization_reference:
            raise AssertionError(f"Missing tokenization merchant reference: {context!r}")

        print("[5/10] Confirm no order, payment, or inventory change exists before callback...")
        if intent.get("order_id") is not None:
            raise AssertionError(f"Order was created before tokenization: {intent!r}")
        if inventory_total(client, ordinary.product_id) != 4:
            raise AssertionError("Ordinary inventory changed during subscription checkout")
        if inventory_total(client, recurring.product_id) != 5:
            raise AssertionError("Subscription inventory changed before schedule acceptance")

        print("[6/10] Verify the navigation-only browser return is processing, not an invalid callback...")
        browser_return = client.request(
            "GET",
            f"/recurring/tokenization/return/{checkout_id}",
            expected_status=202,
            auth=False,
        )
        if "waiting for the secure subscription confirmation" not in browser_return.text.lower():
            raise AssertionError(
                "Navigation-only recurring return did not render processing status: "
                f"{browser_return.text[:500]!r}"
            )
        if "invalid recurring callback" in browser_return.text.lower():
            raise AssertionError("Navigation-only recurring return was treated as a signed callback")

        empty_notify = client.request(
            "POST",
            f"/recurring/tokenization/notify/{checkout_id}",
            expected_status=400,
            form_body={},
            auth=False,
        )
        assert_error_contains(empty_notify, "Invalid recurring callback")
        still_pending = get_one_intent(admin, checkout_id)
        still_pending_context = parse_system_details(still_pending).get("recurring_checkout")
        if not isinstance(still_pending_context, dict) or still_pending_context.get("state") != "TOKENIZATION_PENDING":
            raise AssertionError(f"Rejected empty notify changed recurring state: {still_pending!r}")

        print("[7/10] Record signed tokenization notification and finalize the subscription...")
        token_payload = signed_tokenization_payload(
            tokenization_reference,
            config.tokenization_id,
            config.secret_code,
        )
        notified = client.request(
            "POST",
            f"/recurring/tokenization/notify/{checkout_id}",
            expected_status=200,
            form_body=token_payload,
            auth=False,
        )
        checkout_result = notified.payload.get("checkout") if isinstance(notified.payload, dict) else None
        if not isinstance(checkout_result, dict):
            raise AssertionError(f"Subscription callback response is invalid: {notified.payload!r}")
        if checkout_result.get("requires_one_time_payment") is not False:
            raise AssertionError(f"Subscription unexpectedly requested hosted payment: {checkout_result!r}")
        if checkout_result.get("one_time_payment") is not None:
            raise AssertionError(f"Subscription returned one-time payment details: {checkout_result!r}")
        order_id_value = checkout_result.get("order_id")
        if not isinstance(order_id_value, int):
            raise AssertionError(f"Subscription finalization missing order_id: {checkout_result!r}")
        order_id = order_id_value
        callback_items = checkout_result.get("order_items")
        if not isinstance(callback_items, list) or len(callback_items) != 1:
            raise AssertionError(f"Subscription callback did not return one order item: {checkout_result!r}")
        completed_intent = get_one_intent(admin, checkout_id)
        if completed_intent.get("intent_details") != original_intent_details_raw:
            raise AssertionError("Subscription intent_details changed during trusted recurring workflow")
        completed_context = parse_system_details(completed_intent).get("recurring_checkout")
        if not isinstance(completed_context, dict) or completed_context.get("state") != "COMPLETE":
            raise AssertionError(f"Trusted system_details did not reach COMPLETE: {completed_intent!r}")

        print("[8/10] Verify the navigation-only browser return now reports success...")
        returned = client.request(
            "GET",
            f"/recurring/tokenization/return/{checkout_id}",
            expected_status=200,
            auth=False,
        )
        if "subscription was created successfully" not in returned.text.lower():
            raise AssertionError(f"Subscription return did not render success: {returned.text[:500]!r}")
        if "<form" in returned.text.lower():
            raise AssertionError("Subscription return unexpectedly rendered Standard Hosted Payment")

        print("[9/10] Verify a signed duplicate return remains idempotent...")
        duplicate_return = client.request(
            "POST",
            f"/recurring/tokenization/return/{checkout_id}",
            expected_status=200,
            form_body=token_payload,
            auth=False,
        )
        if "subscription was created successfully" not in duplicate_return.text.lower():
            raise AssertionError(
                f"Signed duplicate subscription return was not idempotent: {duplicate_return.text[:500]!r}"
            )

        print("[10/10] Verify one successful order, one recurring item, no payment row, and inventory...")
        status = client.request("GET", f"/checkout/status/{checkout_id}", expected_status=200).payload
        if not isinstance(status, dict) or status.get("complete") is not True or status.get("success") is not True:
            raise AssertionError(f"Subscription status is not successful: {status!r}")
        if status.get("recurring_checkout_status") != "COMPLETE":
            raise AssertionError(f"Subscription did not reach COMPLETE: {status!r}")

        items_result = client.request(
            "GET",
            "/order_items",
            expected_status=200,
            params={"order_id": order_id},
        )
        items = items_result.payload
        if not isinstance(items, list) or len(items) != 1:
            raise AssertionError(f"Expected exactly one subscription order item: {items!r}")
        recurring_item = items[0]
        recurring_item_ids.append(int(recurring_item["id"]))
        if int(recurring_item.get("product_id") or 0) != recurring.product_id:
            raise AssertionError(f"Recurring item references the wrong product: {recurring_item!r}")
        if int(recurring_item.get("quantity") or 0) != 2:
            raise AssertionError(f"Recurring quantity was not preserved: {recurring_item!r}")
        if Decimal(str(recurring_item.get("amount"))) != Decimal("10.00"):
            raise AssertionError(f"Recurring amount was not quantity-adjusted: {recurring_item!r}")
        if recurring_item.get("recurring_frequency") != "WEEKLY":
            raise AssertionError(f"Recurring frequency was not copied: {recurring_item!r}")
        if recurring_item.get("recurring_intervals") != 1 or recurring_item.get("recurring_total_execution_times") != 2:
            raise AssertionError(f"Recurring terms were not copied: {recurring_item!r}")
        if recurring_item.get("recurring_status") != "ACTIVE" or not recurring_item.get("recurring_merchant_reference"):
            raise AssertionError(f"Recurring schedule is not active: {recurring_item!r}")

        payments = client.request(
            "GET",
            "/payments",
            expected_status=200,
            params={"order_id": order_id},
        ).payload
        if payments not in ([], None):
            raise AssertionError(f"Subscription schedule creation produced a one-time payment row: {payments!r}")
        if inventory_total(client, ordinary.product_id) != 4:
            raise AssertionError("Ordinary inventory changed during subscription checkout")
        if inventory_total(client, recurring.product_id) != 3:
            raise AssertionError("Subscription inventory was not decremented by quantity two")

        cancel_recurring_items(admin, recurring_item_ids)
        print("\nPASS: eStore single-product subscription checkout and navigation-only return verified end to end.")
        return 0
    finally:
        errors: list[str] = []
        if not admin.access_token:
            try:
                admin.login_admin()
            except Exception as exc:
                errors.append(f"admin login for cleanup: {exc}")

        if admin.access_token:
            try:
                cancel_recurring_items(admin, recurring_item_ids)
            except Exception as exc:
                errors.append(f"cancel recurring schedules: {exc}")

        if order_id is not None:
            try:
                delete_orders_direct([order_id])
            except Exception as exc:
                errors.append(f"order {order_id}: {exc}")

        if intent_id is not None and admin.access_token:
            try:
                admin.request(
                    "DELETE",
                    f"/intent/{intent_id}",
                    expected_status=(200, 404),
                )
            except Exception as exc:
                errors.append(f"intent {intent_id}: {exc}")

        for fixture in (recurring, ordinary):
            if fixture is not None:
                try:
                    fixture.cleanup()
                except Exception as exc:
                    errors.append(f"product fixture {fixture.product_id}: {exc}")

        try:
            cleanup_estore_test_customer(
                username,
                customer_id,
                config.timeout,
                label="subscription checkout test cleanup",
            )
        except Exception as exc:
            errors.append(f"customer cleanup: {exc}")

        if errors and sys.exc_info()[0] is None:
            raise AssertionError("Cleanup failed: " + "; ".join(errors))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
