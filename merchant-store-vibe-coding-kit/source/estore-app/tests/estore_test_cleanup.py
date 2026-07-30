"""Cleanup helpers for eStore integration tests."""
from __future__ import annotations

import os
from typing import Optional

import requests

from estore_test_config import biz_admin_credentials, biz_base_url, first_env, load_test_env
from estore_review_test_utils import delete_customers_direct

load_test_env()


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return first_env(name, default=default)


class KeycloakUserCleanup:
    def __init__(self, timeout: int | float = 15) -> None:
        self.timeout = timeout
        self.realm = _env("ESTORE_REALM", "ESTORE")
        base = _env("ESTORE_KC_SERVER_URL") or _env("KC_SERVER_URL", "http://k-keycloak:8080/auth/")
        self.base_url = (base or "").rstrip("/")
        self.client_id = _env("ESTORE_CLIENT_ID", "estore-app")
        self.client_secret = _env("ESTORE_CLIENT_SECRET")
        self._token: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.realm and self.client_id and self.client_secret)

    def _token_url(self) -> str:
        return f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token"

    def _users_url(self) -> str:
        return f"{self.base_url}/admin/realms/{self.realm}/users"

    def token(self) -> str:
        if self._token:
            return self._token
        if not self.configured:
            raise RuntimeError("ESTORE Keycloak cleanup is not configured")
        response = requests.post(
            self._token_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def delete_username(self, username: Optional[str]) -> bool:
        if not username or not self.configured:
            return False
        headers = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}
        found = requests.get(
            self._users_url(),
            headers=headers,
            params={"username": username, "exact": "true"},
            timeout=self.timeout,
        )
        found.raise_for_status()
        deleted = False
        for user in found.json() or []:
            user_id = user.get("id")
            if not user_id:
                continue
            response = requests.delete(f"{self._users_url()}/{user_id}", headers=headers, timeout=self.timeout)
            if response.status_code not in (204, 404):
                response.raise_for_status()
            deleted = True
        # A successful exact lookup with no result also means cleanup is complete.
        return True


def cleanup_keycloak_user(username: Optional[str], timeout: int | float = 15, *, label: str = "cleanup") -> bool:
    try:
        return KeycloakUserCleanup(timeout=timeout).delete_username(username)
    except Exception as exc:
        print(f"  WARNING: {label}: could not delete ESTORE Keycloak user {username}: {exc}")
        return False


class BizCustomerCleanup:
    def __init__(self, timeout: int | float = 15) -> None:
        self.timeout = timeout
        self.base_url = biz_base_url()
        self.username, self.password = biz_admin_credentials(required=False)
        self._token: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    def token(self) -> str:
        if self._token:
            return self._token
        if not self.configured:
            raise RuntimeError("biz customer cleanup credentials are not configured")
        response = requests.post(
            f"{self.base_url}/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("biz /login missing access_token")
        self._token = str(token)
        return self._token

    def delete_customer(self, customer_id: Optional[int]) -> bool:
        if not customer_id or not self.configured:
            return False
        response = requests.delete(
            f"{self.base_url}/customer/{int(customer_id)}",
            headers={"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()
        return True


def cleanup_biz_customer(customer_id: Optional[int], timeout: int | float = 15, *, label: str = "cleanup") -> bool:
    if not customer_id:
        return True
    try:
        if BizCustomerCleanup(timeout=timeout).delete_customer(customer_id):
            return True
    except Exception as exc:
        print(f"  WARNING: {label}: biz-app HTTP customer cleanup failed for {customer_id}: {exc}")

    try:
        delete_customers_direct([int(customer_id)])
        return True
    except Exception as exc:
        print(f"  WARNING: {label}: direct database customer cleanup failed for {customer_id}: {exc}")
        return False


def cleanup_estore_test_customer(
    username: Optional[str],
    customer_id: Optional[int],
    timeout: int | float = 15,
    *,
    label: str = "cleanup",
    require_biz_cleanup: bool = True,
) -> None:
    biz_cleaned = cleanup_biz_customer(customer_id, timeout, label=label)
    keycloak_cleaned = cleanup_keycloak_user(username, timeout, label=label)
    errors: list[str] = []
    if require_biz_cleanup and customer_id and not biz_cleaned:
        errors.append(f"customer row {customer_id} was not cleaned")
    if username and not keycloak_cleaned:
        errors.append(f"Keycloak user {username} was not cleaned")
    if errors:
        raise RuntimeError("; ".join(errors))
