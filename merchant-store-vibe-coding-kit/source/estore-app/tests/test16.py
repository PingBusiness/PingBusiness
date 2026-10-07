#!/usr/bin/env python3
"""Hosted-checkout pass-through contract tests for estore-app."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
SOURCE = APP.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(APP))


def function_source(name: str) -> str:
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(SOURCE, node)
            if segment:
                return segment
    raise AssertionError(f"missing function {name}")


captured: list[dict] = []


def call_pa_checkout(payload):
    captured.append(dict(payload))
    return {
        "action_url": "https://biz.example/crypto/checkout",
        "fields": {"checkout_token": "opaque-token"},
        "merchant_reference": payload["merchant_reference"],
    }, 200


namespace = {
    "Decimal": Decimal,
    "public_base_url": lambda: "https://estore.example",
    "get_customer_ip": lambda: "203.0.113.10",
    "call_pa_checkout": call_pa_checkout,
    "proxy_response": lambda payload, status: (payload, status),
    "error": lambda message, status: ({"error": message}, status),
    "jsonify": lambda payload: payload,
    "html_response": lambda payload: payload,
    "render_template_string": lambda *args, **kwargs: "html",
    "CHECKOUT_AUTOSUBMIT_TEMPLATE": "template",
    "ESTORE_CHECKOUT_LANG": None,
}
exec("from __future__ import annotations\n" + function_source("render_standard_payment_checkout"), namespace)
render = namespace["render_standard_payment_checkout"]


def invoke(network: str):
    captured.clear()
    result = render(
        intent_id=123,
        intent_identifier="intent-uuid",
        merchant_reference="merchant-ref",
        currency="HKD",
        amount=Decimal("100.00"),
        customer={
            "first_name": "Test",
            "last_name": "Customer",
            "billing_address": "1 Test Street",
            "phone": "12345678",
            "email": "test@example.test",
        },
        selected_network=network,
        response_mode="json",
    )
    return result


def main() -> int:
    print("[1/4] Existing estore -> biz checkout endpoint remains /pa/checkout...")
    call_src = function_source("call_pa_checkout")
    assert '"/pa/checkout"' in call_src or "'/pa/checkout'" in call_src

    print("[2/4] Crypto is forwarded unchanged as the selected network...")
    payload, status = invoke("Crypto")
    assert status == 200
    assert len(captured) == 1
    assert captured[0]["network"] == "Crypto"

    print("[3/4] Generic action_url + fields are returned unchanged...")
    assert payload == {
        "checkout_id": "intent-uuid",
        "checkout_reference": "merchant-ref",
        "action_url": "https://biz.example/crypto/checkout",
        "fields": {"checkout_token": "opaque-token"},
    }

    print("[4/4] PaymentAsia networks use the exact same estore path...")
    cc_payload, cc_status = invoke("CreditCard")
    assert cc_status == 200
    assert captured[0]["network"] == "CreditCard"
    assert cc_payload["action_url"] == "https://biz.example/crypto/checkout"
    assert cc_payload["fields"] == {"checkout_token": "opaque-token"}

    print("\nPASS: estore treats Crypto as a generic hosted checkout network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
