#!/usr/bin/env python3
"""
PingBiz estore auth bridge test client.

This client follows the login pattern used by app/estore/tests/test1.py:

    1. GET /health
    2. POST /customer to create a fresh customer in the configured estore context
    3. POST /login with that customer username/password
    4. GET /user?username=... using the login access token
    5. POST /refresh using the refresh token returned by /login
    6. GET /user?username=... using the refreshed access token
    7. POST /logout using the refresh token
    8. POST /refresh again and expect failure after logout

It deliberately does not contact Keycloak directly. All auth calls go through
estore app.py, just like the Angular KeycloakService.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The requests package is required. Install with: python3 -m pip install -r requirements.txt"
    ) from exc

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from estore_test_config import estore_base_url, load_test_env
from estore_test_cleanup import cleanup_estore_test_customer


JsonMap = Dict[str, Any]
ExpectedStatus = Union[int, List[int], Iterable[int]]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    status_code: Optional[int] = None


@dataclass
class TestConfig:
    base_url: str
    timeout: float
    username_prefix: str
    password: str
    existing_username: Optional[str]
    existing_password: Optional[str]
    verify_tls: bool
    verbose: bool
    skip_logout: bool
    logout_token_mode: str


class EStoreAuthTestClient:
    def __init__(self, base_url: str, timeout: float = 15.0, verify_tls: bool = True, verbose: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.verbose = verbose
        self.session = requests.Session()

    def _print_verbose(self, message: str) -> None:
        if self.verbose:
            print(message)

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def headers(self, access_token: Optional[str] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[JsonMap] = None,
        params: Optional[JsonMap] = None,
        access_token: Optional[str] = None,
        expected: Optional[ExpectedStatus] = None,
    ) -> Tuple[requests.Response, Any]:
        url = self.url(path)
        expected_set = normalize_expected(expected)

        self._print_verbose(f"\n> {method.upper()} {url}")
        if params:
            self._print_verbose(f"params={json.dumps(params, sort_keys=True)}")
        if json_body is not None:
            self._print_verbose(json.dumps(redact_tokens(json_body), indent=2, sort_keys=True))

        response = self.session.request(
            method=method.upper(),
            url=url,
            json=json_body,
            params=params,
            headers=self.headers(access_token),
            timeout=self.timeout,
            verify=self.verify_tls,
        )

        if response.status_code == 204:
            payload: Any = None
        else:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text

        self._print_verbose(f"< HTTP {response.status_code}")
        if self.verbose:
            if isinstance(payload, (dict, list)):
                print(json.dumps(redact_tokens(payload), indent=2, sort_keys=True))
            elif payload:
                print(str(payload)[:1000])

        if expected_set is not None and response.status_code not in expected_set:
            hint = login_failure_hint(path, response.status_code, payload)
            raise AssertionError(
                f"Expected HTTP {sorted(expected_set)} from {method.upper()} {path}; "
                f"got HTTP {response.status_code}: {redact_tokens(payload)}{hint}"
            )

        return response, payload

    def health(self) -> Tuple[requests.Response, JsonMap]:
        response, payload = self.request("GET", "/health", expected=200)
        if not isinstance(payload, dict):
            raise AssertionError(f"/health returned non-JSON payload: {payload!r}")
        return response, payload

    def create_customer(self, username: str, password: str) -> Tuple[requests.Response, JsonMap]:
        body = {
            "username": username,
            "email": username,
            "password": password,
            "first_name": "Auto",
            "last_name": "Customer",
            "details": "auth bridge test customer",
            "shipping_address": "100 Auth Test Ship Road",
            "billing_address": "200 Auth Test Bill Road",
            "phone": "14165550123",
        }
        response, payload = self.request("POST", "/customer", json_body=body, expected=201)
        if not isinstance(payload, dict):
            raise AssertionError(f"/customer returned non-JSON payload: {payload!r}")
        require_fields(payload, ["id", "keycloak_user_id"], "/customer")
        return response, payload

    def login(self, username: str, password: str) -> Tuple[requests.Response, JsonMap]:
        response, payload = self.request(
            "POST",
            "/login",
            json_body={"username": username, "password": password},
            expected=200,
        )
        if not isinstance(payload, dict):
            raise AssertionError(f"/login returned non-JSON payload: {payload!r}")
        require_fields(payload, ["access_token", "refresh_token", "expires_in", "refresh_expires_in"], "/login")
        return response, payload

    def get_user(self, access_token: str, username: Optional[str] = None) -> Tuple[requests.Response, JsonMap]:
        path = "/user"
        if username:
            path += f"?username={quote(username)}"
        response, payload = self.request("GET", path, access_token=access_token, expected=200)
        if not isinstance(payload, dict):
            raise AssertionError(f"/user returned non-JSON payload: {payload!r}")
        require_any_field(payload, ["sub", "username", "id", "email", "customer", "customer_id"], "/user")
        return response, payload

    def refresh(self, refresh_token: str, expected: ExpectedStatus = 200) -> Tuple[requests.Response, Any]:
        response, payload = self.request(
            "POST",
            "/refresh",
            json_body={"refresh_token": refresh_token},
            expected=expected,
        )
        if normalize_expected(expected) == {200}:
            if not isinstance(payload, dict):
                raise AssertionError(f"/refresh returned non-JSON payload: {payload!r}")
            require_fields(payload, ["access_token", "expires_in"], "/refresh")
        return response, payload

    def logout(self, refresh_token: str) -> Tuple[requests.Response, Any]:
        return self.request("POST", "/logout", json_body={"refresh_token": refresh_token}, expected=200)

    def expect_status(
        self,
        check_name: str,
        method: str,
        path: str,
        expected: ExpectedStatus,
        *,
        json_body: Optional[JsonMap] = None,
        access_token: Optional[str] = None,
    ) -> CheckResult:
        try:
            response, _payload = self.request(
                method,
                path,
                json_body=json_body,
                access_token=access_token,
                expected=expected,
            )
            return CheckResult(check_name, True, f"HTTP {response.status_code} as expected", response.status_code)
        except Exception as exc:
            return CheckResult(check_name, False, str(exc), None)


class TestRunner:
    def __init__(self, client: EStoreAuthTestClient, config: TestConfig) -> None:
        self.client = client
        self.config = config
        self.results: list[CheckResult] = []
        self.username = ""
        self.password = ""
        self.created_customer: Optional[JsonMap] = None
        self.tokens: JsonMap = {}
        self.user_before_refresh: Optional[JsonMap] = None
        self.user_after_refresh: Optional[JsonMap] = None
        self.step_no = 0
        self.total_steps = 8

    def step(self, message: str) -> None:
        self.step_no += 1
        print(f"[{self.step_no}/{self.total_steps}] {message}...")

    def add_result(self, name: str, fn, *args, **kwargs) -> Any:
        started = time.time()
        try:
            value = fn(*args, **kwargs)
            elapsed_ms = int((time.time() - started) * 1000)
            status_code: Optional[int] = None
            if isinstance(value, tuple) and value and hasattr(value[0], "status_code"):
                status_code = int(value[0].status_code)
            self.results.append(CheckResult(name, True, f"passed in {elapsed_ms} ms", status_code))
            return value
        except Exception as exc:
            elapsed_ms = int((time.time() - started) * 1000)
            self.results.append(CheckResult(name, False, f"failed in {elapsed_ms} ms: {exc}"))
            return None

    def choose_test_identity(self) -> None:
        if self.config.existing_username and self.config.existing_password:
            self.username = self.config.existing_username
            self.password = self.config.existing_password
            return

        run_id = uuid.uuid4().hex[:12]
        prefix = self.config.username_prefix or "AUTO_ESTORE_AUTH"
        self.username = f"{prefix}_{run_id}@example.test".lower()
        self.password = self.config.password

    def run(self) -> bool:
        self.choose_test_identity()
        self.total_steps = 7 if self.config.skip_logout else 8

        self.step("GET /health")
        self.add_result("GET /health", self.client.health)

        self.step("Create fresh auth test customer")
        if not self.config.existing_username:
            created = self.add_result("POST /customer create fresh auth test customer", self.client.create_customer, self.username, self.password)
            if not created:
                return self.passed()
            _, self.created_customer = created
        else:
            self.results.append(CheckResult("POST /customer create fresh auth test customer", True, "skipped; using existing credentials"))

        self.step("POST /login")
        login_result = self.add_result("POST /login", self.client.login, self.username, self.password)
        if not login_result:
            return self.passed()
        _, login_payload = login_result
        self.tokens = dict(login_payload)
        access_token = self.tokens["access_token"]
        original_refresh_token = self.tokens["refresh_token"]

        self.step("GET /user with login access token")
        user_result = self.add_result("GET /user with login access token", self.client.get_user, access_token, self.username)
        if user_result:
            _, self.user_before_refresh = user_result
            self.validate_user_matches_created_customer(self.user_before_refresh)

        self.step("POST /refresh")
        refresh_result = self.add_result("POST /refresh", self.client.refresh, original_refresh_token)
        if not refresh_result:
            return self.passed()
        _, refresh_payload = refresh_result
        refreshed_access_token = refresh_payload["access_token"]

        self.step("GET /user with refreshed access token")
        refreshed_user_result = self.add_result(
            "GET /user with refreshed access token",
            self.client.get_user,
            refreshed_access_token,
            self.username,
        )
        if refreshed_user_result:
            _, self.user_after_refresh = refreshed_user_result
            self.validate_user_matches_created_customer(self.user_after_refresh)

        self.step("POST /logout")
        if self.config.skip_logout:
            self.results.append(CheckResult("POST /logout", True, "skipped by --skip-logout"))
            return self.passed()

        logout_refresh_token = self.select_logout_token(original_refresh_token, refresh_payload)
        logout_result = self.add_result("POST /logout", self.client.logout, logout_refresh_token)
        if logout_result:
            self.step("POST /refresh after logout should fail")
            self.results.append(
                self.client.expect_status(
                    "POST /refresh after logout should fail",
                    "POST",
                    "/refresh",
                    {400, 401},
                    json_body={"refresh_token": logout_refresh_token},
                )
            )

        return self.passed()

    def validate_user_matches_created_customer(self, user_payload: JsonMap) -> None:
        if not self.created_customer:
            return
        created_id = self.created_customer.get("id")
        user_id = user_payload.get("id") or user_payload.get("customer_id")
        if isinstance(user_payload.get("customer"), dict):
            user_id = user_payload["customer"].get("id", user_id)
        if user_id is not None and created_id is not None and int(user_id) != int(created_id):
            raise AssertionError(f"/user returned customer id {user_id}, expected {created_id}: {user_payload!r}")

    def select_logout_token(self, original_refresh_token: str, refresh_payload: JsonMap) -> str:
        mode = self.config.logout_token_mode
        rotated = refresh_payload.get("refresh_token") if isinstance(refresh_payload, dict) else None
        if mode == "rotated":
            if not rotated:
                raise AssertionError("--logout-token rotated was requested but /refresh returned no refresh_token")
            return str(rotated)
        if mode == "auto" and rotated:
            return str(rotated)
        return original_refresh_token

    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def print_summary(self, json_output: bool = False) -> None:
        if json_output:
            summary = {
                "passed": self.passed(),
                "username": self.username,
                "created_customer": redact_tokens(self.created_customer),
                "checks": [result.__dict__ for result in self.results],
                "user_before_refresh": redact_tokens(self.user_before_refresh),
                "user_after_refresh": redact_tokens(self.user_after_refresh),
            }
            print(json.dumps(summary, indent=2, sort_keys=True))
            return

        print("\nEstore auth bridge test summary")
        print("=" * 38)
        print(f"Base URL: {self.config.base_url}")
        print(f"Username tested: {self.username or 'not selected'}")
        for idx, result in enumerate(self.results, start=1):
            status = f" HTTP {result.status_code}" if result.status_code is not None else ""
            outcome = "ok" if result.passed else "failed"
            print(f"[{idx}/{len(self.results)}] {result.name}{status} - {outcome}: {result.detail}")

        if self.user_after_refresh:
            user_label = (
                self.user_after_refresh.get("email")
                or self.user_after_refresh.get("username")
                or self.user_after_refresh.get("sub")
                or "unknown"
            )


def normalize_expected(expected: Optional[ExpectedStatus]) -> Optional[set[int]]:
    if expected is None:
        return None
    if isinstance(expected, int):
        return {expected}
    return {int(item) for item in expected}


def require_fields(payload: JsonMap, fields: Iterable[str], endpoint: str) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        safe_payload = redact_tokens(payload)
        raise AssertionError(f"{endpoint} response missing required fields {missing}; payload={safe_payload}")


def require_any_field(payload: JsonMap, fields: Iterable[str], endpoint: str) -> None:
    if not any(payload.get(field) is not None for field in fields):
        safe_payload = redact_tokens(payload)
        raise AssertionError(f"{endpoint} response did not include any of {list(fields)}; payload={safe_payload}")


def login_failure_hint(path: str, status_code: int, payload: Any) -> str:
    if path != "/login":
        return ""
    text = json.dumps(payload, default=str).lower() if isinstance(payload, (dict, list)) else str(payload).lower()
    if status_code in {400, 401} and ("invalid_grant" in text or "invalid user credentials" in text):
        return (
            "\nHint: Keycloak returned invalid credentials. This client now creates a fresh "
            "customer before login unless --existing-username is supplied. If you used "
            "--existing-username, verify the account exists in the ESTORE realm, the password "
            "matches, and the estore backend is configured for the same realm/client."
        )
    return ""


def redact_tokens(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: JsonMap = {}
        for key, item in value.items():
            key_lower = key.lower()
            if "token" in key_lower or key_lower in {"authorization", "password", "secret"}:
                redacted[key] = redact_string(item)
            else:
                redacted[key] = redact_tokens(item)
        return redacted
    if isinstance(value, list):
        return [redact_tokens(item) for item in value]
    return value


def redact_string(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 12:
        return "***"
    return f"{text[:6]}...{text[-6:]}"


def env_default(*names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    if load_dotenv is not None:
        load_test_env()

    parser = argparse.ArgumentParser(
        description="Test estore app.py backend-mediated login, refresh-token use, and logout.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Default test1.py-style flow creates a fresh customer, then logs in:
              ESTORE_APP_BASE_URL=http://localhost:5001 \\
              ESTORE_TEST_PASSWORD='TestPassword123!' \\
                python3 estore_auth_test_client.py

            To reproduce a login failure for an existing user without creating a customer:
              python3 estore_auth_test_client.py \\
                --existing-username customer@example.com \\
                --existing-password 'secret' \\
                --verbose
            """
        ),
    )
    parser.add_argument(
        "--base-url",
        default=env_default("ESTORE_APP_BASE_URL", "APP_URL", "ESTORE_APP_URL", default=estore_base_url()),
        help="Estore backend base URL. Defaults to ESTORE_APP_BASE_URL, APP_URL, ESTORE_APP_URL, then http://estore-app:5000.",
    )
    parser.add_argument(
        "--username-prefix",
        default=env_default("ESTORE_TEST_USERNAME_PREFIX", default="AUTO_ESTORE_AUTH"),
        help="Prefix for the fresh test customer username. Defaults to ESTORE_TEST_USERNAME_PREFIX.",
    )
    parser.add_argument(
        "--password",
        default=env_default("ESTORE_TEST_PASSWORD", "ESTORE_PASSWORD", default="TestPassword123!"),
        help="Password used when creating the fresh test customer. Defaults to ESTORE_TEST_PASSWORD.",
    )
    parser.add_argument(
        "--existing-username",
        default=env_default("ESTORE_EXISTING_USERNAME", "ESTORE_USERNAME", default=None),
        help="Optional existing customer username. If supplied with --existing-password, customer creation is skipped.",
    )
    parser.add_argument(
        "--existing-password",
        default=env_default("ESTORE_EXISTING_PASSWORD", default=None),
        help="Optional existing customer password. If supplied with --existing-username, customer creation is skipped.",
    )
    parser.add_argument("--timeout", type=float, default=float(os.getenv("ESTORE_TEST_TIMEOUT", os.getenv("ESTORE_APP_TIMEOUT", "20"))))
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification for HTTPS test environments.")
    parser.add_argument("--skip-logout", action="store_true", help="Do not call /logout; useful when debugging credentials.")
    parser.add_argument(
        "--logout-token",
        choices=["original", "rotated", "auto"],
        default=os.getenv("ESTORE_LOGOUT_TOKEN_MODE", "original"),
        help=(
            "Refresh token to send to /logout after /refresh. 'original' matches the provided Angular KeycloakService; "
            "'rotated' requires /refresh to return a refresh_token; 'auto' uses a returned refresh_token when present."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Print request/response details with tokens redacted.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    return parser.parse_args(argv)


def load_config(argv: Optional[list[str]] = None) -> Tuple[TestConfig, bool]:
    args = parse_args(argv)

    existing_username = args.existing_username
    existing_password = args.existing_password
    if bool(existing_username) != bool(existing_password):
        raise RuntimeError("Supply both --existing-username and --existing-password, or neither.")

    if not args.base_url:
        raise RuntimeError("Missing --base-url / ESTORE_APP_BASE_URL / APP_URL")
    if not args.password and not existing_password:
        raise RuntimeError("Missing --password / ESTORE_TEST_PASSWORD")

    config = TestConfig(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout,
        username_prefix=args.username_prefix,
        password=args.password,
        existing_username=existing_username,
        existing_password=existing_password,
        verify_tls=not args.insecure,
        verbose=args.verbose,
        skip_logout=args.skip_logout,
        logout_token_mode=args.logout_token,
    )
    return config, bool(args.json)


def main(argv: Optional[list[str]] = None) -> int:
    try:
        config, json_output = load_config(argv)
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    client = EStoreAuthTestClient(
        config.base_url,
        timeout=config.timeout,
        verify_tls=config.verify_tls,
        verbose=config.verbose,
    )
    runner = TestRunner(client, config)
    try:
        runner.run()
    except requests.RequestException as exc:
        runner.results.append(CheckResult("HTTP client", False, str(exc)))
    finally:
        runner.print_summary(json_output=json_output)
        if not config.existing_username:
            customer_id = None
            if isinstance(runner.created_customer, dict) and isinstance(runner.created_customer.get("id"), int):
                customer_id = int(runner.created_customer["id"])
            cleanup_estore_test_customer(runner.username, customer_id, config.timeout, label="test3 cleanup")

    passed = runner.passed()
    if not json_output:
        if passed:
            print("\nPASS: estore-app auth bridge checks passed.", flush=True)
        else:
            print("\nFAIL: estore-app auth bridge checks failed.", flush=True)

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())



