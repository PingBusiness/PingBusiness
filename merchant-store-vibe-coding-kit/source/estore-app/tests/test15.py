#!/usr/bin/env python3
"""Crypto checkout-network parser regression tests for estore-app."""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
SOURCE = APP.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(APP))

wanted_assignments = {"PAYMENT_ASIA_NETWORKS", "PAYMENT_ASIA_NETWORK_SET", "CHECKOUT_NETWORK_SET"}
nodes = []
for node in TREE.body:
    if isinstance(node, ast.Assign):
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if names & wanted_assignments:
            nodes.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name == "parse_payment_networks":
        nodes.append(node)

namespace: dict[str, object] = {}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), "exec"), namespace)

PAYMENT_ASIA_NETWORK_SET = namespace["PAYMENT_ASIA_NETWORK_SET"]
CHECKOUT_NETWORK_SET = namespace["CHECKOUT_NETWORK_SET"]
parse_payment_networks = namespace["parse_payment_networks"]


def must_raise(value: object, needle: str) -> None:
    try:
        parse_payment_networks(value)
    except ValueError as exc:
        if needle.lower() not in str(exc).lower():
            raise AssertionError(f"expected {needle!r} in {exc!r}")
    else:
        raise AssertionError(f"expected ValueError for {value!r}")


def main() -> int:
    print("[1/5] Crypto is checkout-only, not a PaymentAsia network...")
    assert "Crypto" in CHECKOUT_NETWORK_SET
    assert "Crypto" not in PAYMENT_ASIA_NETWORK_SET

    print("[2/5] Existing PaymentAsia networks remain accepted...")
    for network in sorted(PAYMENT_ASIA_NETWORK_SET):
        assert parse_payment_networks(network) == [network]

    print("[3/5] Mixed merchant configuration accepts Crypto...")
    assert parse_payment_networks("CreditCard,Fps,Crypto") == ["CreditCard", "Fps", "Crypto"]

    print("[4/5] Unknown, empty and duplicate networks remain rejected...")
    must_raise("CreditCard,NotARealNetwork", "unsupported")
    must_raise("CreditCard,,Crypto", "empty")
    must_raise("Crypto,Crypto", "duplicate")

    print("[5/5] Whitespace normalization still works...")
    assert parse_payment_networks(" CreditCard , Crypto ") == ["CreditCard", "Crypto"]

    print("\nPASS: estore checkout-network parser adds Crypto without widening PaymentAsia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
