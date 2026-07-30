#!/usr/bin/env python3
"""Static regression guard for trusted Standard checkout claiming.

The merchant-hosted estore-app may request checkout, but it must not claim the
intent by writing status after the launch response. biz-app owns that transition.
"""
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def main() -> int:
    source = APP_PATH.read_text(encoding="utf-8")
    start = source.index("def render_standard_payment_checkout(")
    end = source.index("def callback_payload()", start)
    render_source = source[start:end]

    if "call_pa_checkout(pa_body)" not in render_source:
        raise AssertionError("Standard checkout no longer calls the trusted biz-app proxy")
    if "update_intent_status(" in render_source:
        raise AssertionError("estore-app still performs the untrusted post-checkout status write")
    if "def update_intent_status(" in source:
        raise AssertionError("Obsolete eStore intent-status mutation helper remains")

    print("PASS: estore-app delegates the one-time checkout claim entirely to biz-app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
