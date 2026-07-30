#!/usr/bin/env python3
"""Run the idempotent realm reconciliation and operational verification."""

from __future__ import annotations

from reconcile_realm import main as reconcile
from verify_realm import main as verify


def main() -> int:
    result = reconcile()
    if result != 0:
        return result
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
