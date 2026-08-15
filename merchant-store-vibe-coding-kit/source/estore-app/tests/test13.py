#!/usr/bin/env python3
"""Fail-closed customer-token introspection regression test.

Authentication succeeds only when Keycloak returns the literal JSON boolean
``active: true`` and a non-empty subject. This test executes the real
``introspect_customer_token`` function with mocked HTTP responses and requires
no running services.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[3]
APP_PATH = ROOT / "app" / "estore" / "app.py"


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


class FakeRequests:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def post(self, url: str, *, data: Dict[str, Any], timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        return self.response


def load_function():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APP_PATH))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "introspect_customer_token"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: Dict[str, Any] = {
        "ESTORE_INTROSPECT_URL": "https://keycloak.test/introspect",
        "ESTORE_CLIENT_ID": "estore-test",
        "ESTORE_CLIENT_SECRET": "secret",
        "Dict": Dict,
        "Any": Any,
    }
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace["introspect_customer_token"], namespace


def expect_rejected(fn, namespace: Dict[str, Any], payload: Any) -> None:
    fake = FakeRequests(FakeResponse(payload))
    namespace["requests"] = fake
    try:
        fn("token")
    except PermissionError:
        pass
    else:
        raise AssertionError(f"Expected payload to be rejected: {payload!r}")
    if len(fake.calls) != 1:
        raise AssertionError("Expected exactly one introspection request")


def main() -> int:
    fn, namespace = load_function()

    print("[1/5] Literal active=true with subject is accepted...")
    fake = FakeRequests(FakeResponse({"active": True, "sub": "customer-123"}))
    namespace["requests"] = fake
    result = fn("token")
    if result.get("sub") != "customer-123":
        raise AssertionError(f"Unexpected accepted payload: {result!r}")

    print("[2/5] False, missing, and null active values are rejected...")
    for payload in ({"active": False, "sub": "x"}, {"sub": "x"}, {"active": None, "sub": "x"}):
        expect_rejected(fn, namespace, payload)

    print("[3/5] Truthy non-boolean active values are rejected...")
    for value in (1, "true", "yes", [], {}):
        expect_rejected(fn, namespace, {"active": value, "sub": "x"})

    print("[4/5] Missing subject is rejected...")
    expect_rejected(fn, namespace, {"active": True})

    print("[5/5] Customer update path retains the same strict boolean guard...")
    source = APP_PATH.read_text(encoding="utf-8")
    if 'if token_info.get("active") is not True:' not in source:
        raise AssertionError("Customer update path is not using strict active boolean validation")

    print("PASS: eStore customer-token introspection fails closed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise
