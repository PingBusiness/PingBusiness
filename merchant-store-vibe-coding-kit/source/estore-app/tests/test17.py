#!/usr/bin/env python3
"""Merchant payment-configuration compatibility tests for estore-app."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[1] / "app.py"
SOURCE = APP.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(APP))


def select_nodes():
    wanted_assignments = {"PAYMENT_ASIA_NETWORKS", "PAYMENT_ASIA_NETWORK_SET", "CHECKOUT_NETWORK_SET"}
    wanted_functions = {"parse_payment_networks", "get_configured_payment_networks"}
    out = []
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted_assignments:
                out.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            out.append(node)
    return out


class Logger:
    def error(self, *args, **kwargs):
        pass


merchant_box = {
    "value": {
        "payment_gateway": "PAYMENT_ASIA",
        "payment_networks": "CreditCard,Crypto",
    }
}


def get_configured_merchant():
    return dict(merchant_box["value"]), None


def error(message, status):
    return {"error": message}, status


namespace = {
    "get_configured_merchant": get_configured_merchant,
    "proxy_response": lambda payload, status: (payload, status),
    "error": error,
    "app": SimpleNamespace(logger=Logger()),
}
module = ast.Module(body=select_nodes(), type_ignores=[])
exec(compile(module, str(APP), "exec"), namespace)
get_configured_payment_networks = namespace["get_configured_payment_networks"]


def main() -> int:
    print("[1/4] PAYMENT_ASIA remains the merchant gateway value...")
    config, err = get_configured_payment_networks()
    assert err is None
    assert config == {
        "payment_gateway": "PAYMENT_ASIA",
        "payment_networks": ["CreditCard", "Crypto"],
    }

    print("[2/4] Crypto does not require a new gateway type...")
    merchant_box["value"] = {
        "payment_gateway": "CRYPTO",
        "payment_networks": "Crypto",
    }
    config, err = get_configured_payment_networks()
    assert config is None
    assert err[1] == 400
    assert "PaymentAsia" in err[0]["error"]

    print("[3/4] Invalid merchant network configuration still fails closed...")
    merchant_box["value"] = {
        "payment_gateway": "PAYMENT_ASIA",
        "payment_networks": "CreditCard,EvilNetwork",
    }
    config, err = get_configured_payment_networks()
    assert config is None
    assert err[1] == 502

    print("[4/4] No Crypto provider implementation leaked into estore-app...")
    forbidden = ("CryptoRouter", "crypto-app", "CRYPTO_ROUTER", "CRYPTO_OPERATOR_PRIVATE_KEY")
    for needle in forbidden:
        assert needle not in SOURCE, f"estore-app unexpectedly contains provider-specific Crypto logic: {needle}"

    print("\nPASS: estore remains provider-agnostic and backward compatible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
