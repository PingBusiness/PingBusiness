#!/usr/bin/env python3
"""Subscription checkout compatibility regressions: python app/estore/tests/test18.py.

Executes the production estore subscription functions with mocked biz HTTP. The
estore remains provider-agnostic: it sends immutable subscription terms to
biz-app and follows the returned hosted checkout link.
"""
from __future__ import annotations

import ast
import copy
import json
import unittest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

APP = Path(__file__).resolve().parents[1] / "app.py"
SOURCE = APP.read_text(encoding="utf-8")
FUNCTIONS = set("""
parse_int decimal_from_value product_recurring_plan next_recurring_start_date
build_checkout_line build_checkout build_subscription checkout_snapshot_line subscribe
call_recurring_checkout create_intent extract_recurring_redirect_link
""".split())


def load_functions(ns):
    nodes = []
    for node in ast.parse(SOURCE, filename=str(APP)).body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            node.decorator_list = []
            nodes.append(node)
    if {node.name for node in nodes} != FUNCTIONS:
        raise AssertionError("Missing production subscription function")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, str(APP), "exec"), ns)


class EstoreSubscriptionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.product = {
            "id": 4, "name": "Subscription", "currency": "HKD", "amount": "25.50",
            "recurring_frequency": "MONTHLY", "recurring_intervals": 3,
            "recurring_total_execution_times": 12,
        }
        self.body = {"product_id": 4, "quantity": 2}
        self.calls = []
        self.available = 20
        self.intent = None
        self.provider_error = False
        self.redirect_link = "https://biz.example/subscription/c/intent-uuid?token=opaque"
        self.customer = {"id": 3, "first_name": "Test", "last_name": "Customer"}
        self.ns = dict(
            Decimal=Decimal, InvalidOperation=InvalidOperation, json=json, uuid=uuid, urlparse=urlparse,
            datetime=datetime, timedelta=timedelta, HONG_KONG_TZ=ZoneInfo("Asia/Hong_Kong"),
            ESTORE_STORE_ID_INT=2, app=SimpleNamespace(logger=Mock()), request=SimpleNamespace(json=self.body),
            require_current_customer=lambda: (self.customer, None),
            validate_product_scope=lambda product_id: (copy.deepcopy(self.product), None),
            biz_request=self.biz_request,
            public_base_url=lambda: "https://estore.example",
            get_customer_ip=lambda: "203.0.113.1",
            error=lambda message, status: ({"error": message}, status),
            proxy_response=lambda payload, status: (payload, status),
            html_response=lambda value: ({"html": value}, 200),
            render_template_string=lambda template, **kw: {"template": template, **kw},
            RECURRING_REDIRECT_TEMPLATE="recurring",
        )
        load_functions(self.ns)

    def biz_request(self, method, path, *, json_body=None, params=None):
        self.calls.append((method, path, copy.deepcopy(json_body)))
        if path == "/inventories":
            return [{"quantity": self.available}], 200
        if path == "/intent":
            self.intent = copy.deepcopy(json_body)
            self.intent["intent_details"] = json.loads(self.intent["intent_details"])
            return {"id": 6, "identifier": "intent-uuid"}, 201
        if path == "/recurring/checkout":
            if self.provider_error:
                return {"error": "provider unavailable"}, 503
            return {"accepted": True, "redirect_link": self.redirect_link}, 200
        raise AssertionError(f"Unexpected biz request: {method} {path}")

    def subscribe(self):
        self.ns["request"].json = self.body
        return self.ns["subscribe"]()

    def requests_for(self, path):
        return [payload for _, route, payload in self.calls if route == path]

    def test_hkd_subscription_keeps_installment_amount_and_terms(self):
        result, status = self.subscribe()
        self.assertEqual(status, 200)
        self.assertEqual(result["html"]["template"], "recurring")
        self.assertEqual(result["html"]["redirect_link"], self.redirect_link)
        self.assertEqual(self.intent["currency"], "HKD")
        self.assertEqual(self.intent["amount"], "51.00")  # one installment: 25.50 x quantity 2
        details = self.intent["intent_details"]
        self.assertEqual(details["checkout_kind"], "subscription")
        self.assertNotIn("payment_network", details)
        line = details["line_items"][0]
        self.assertEqual(line["unit_amount"], "25.50")
        self.assertEqual(line["amount"], "51.00")
        self.assertEqual(line["recurring_intervals"], 3)
        self.assertEqual(line["recurring_total_execution_times"], 12)
        self.assertEqual(len(self.requests_for("/recurring/checkout")), 1)
        recurring = self.requests_for("/recurring/checkout")[0]
        self.assertEqual(recurring.get("subscription_payment_version"), 2)
        self.assertNotIn("/pa/checkout", [route for _, route, _ in self.calls])

    def test_non_hkd_subscriptions_are_no_longer_rejected_by_estore(self):
        for currency in ("USD", "EUR", "CAD"):
            with self.subTest(currency=currency):
                self.calls.clear()
                self.product["currency"] = currency
                result, status = self.subscribe()
                self.assertEqual(status, 200)
                self.assertEqual(self.intent["currency"], currency)
                self.assertEqual(self.intent["amount"], "51.00")
                self.assertEqual(result["html"]["redirect_link"], self.redirect_link)

    def test_estore_does_not_choose_or_require_payment_method(self):
        # Browser-supplied network is intentionally ignored; biz-app's hosted
        # selector owns the payment-method decision.
        for supplied in (None, "CreditCard", "Fps", "Crypto", "NotEnabled"):
            with self.subTest(supplied=supplied):
                self.calls.clear()
                if supplied is None:
                    self.body.pop("network", None)
                else:
                    self.body["network"] = supplied
                self.assertEqual(self.subscribe()[1], 200)
                self.assertNotIn("payment_network", self.intent["intent_details"])
                recurring = self.requests_for("/recurring/checkout")[0]
                self.assertNotIn("network", recurring)
        tree = ast.parse(SOURCE, filename=str(APP))
        subscribe_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "subscribe")
        subscribe_source = ast.get_source_segment(SOURCE, subscribe_node) or ""
        self.assertNotIn("get_configured_payment_networks()", subscribe_source)

    def test_interval_length_does_not_change_estore_installment_amount(self):
        for interval in (1, 2, 7):
            with self.subTest(interval=interval):
                self.calls.clear()
                self.product["recurring_intervals"] = interval
                self.product["recurring_total_execution_times"] = 5
                self.assertEqual(self.subscribe()[1], 200)
                self.assertEqual(self.intent["amount"], "51.00")
                line = self.intent["intent_details"]["line_items"][0]
                self.assertEqual(line["recurring_intervals"], interval)
                self.assertEqual(line["recurring_total_execution_times"], 5)

    def test_customer_cannot_override_price_currency_or_subscription_terms(self):
        self.body.update({
            "amount": "0.01", "currency": "USD", "network": "Crypto",
            "recurring_intervals": 1, "recurring_total_execution_times": 1,
            "line_items": [{"amount": "0.01"}],
        })
        self.assertEqual(self.subscribe()[1], 200)
        self.assertEqual(self.intent["amount"], "51.00")
        self.assertEqual(self.intent["currency"], "HKD")
        line = self.intent["intent_details"]["line_items"][0]
        self.assertEqual(line["recurring_intervals"], 3)
        self.assertEqual(line["recurring_total_execution_times"], 12)

    def test_stock_quantity_and_subscription_kind_remain_enforced(self):
        self.body["quantity"] = 0
        self.assertEqual(self.subscribe()[1], 400)
        self.body["quantity"] = 2
        self.available = 1
        self.assertEqual(self.subscribe()[1], 400)
        self.available = 20
        for key in ("recurring_frequency", "recurring_intervals", "recurring_total_execution_times"):
            self.product[key] = None
        self.assertEqual(self.subscribe()[1], 400)

    def test_subscription_still_cannot_enter_ordinary_cart(self):
        with self.assertRaisesRegex(ValueError, "Subscribe Now"):
            self.ns["build_checkout"]([{"product_id": 4, "quantity": 2}])

    def test_biz_checkout_failure_is_propagated(self):
        self.provider_error = True
        body, status = self.subscribe()
        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "provider unavailable")

    def test_existing_hkd_card_fast_path_remains_compatible_with_same_redirect_contract(self):
        self.redirect_link = "https://pa.example/tokenize"
        result, status = self.subscribe()
        self.assertEqual(status, 200)
        self.assertEqual(result["html"]["redirect_link"], "https://pa.example/tokenize")


if __name__ == "__main__":
    unittest.main(verbosity=2)
