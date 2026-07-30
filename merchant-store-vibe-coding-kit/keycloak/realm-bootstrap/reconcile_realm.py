#!/usr/bin/env python3
"""Idempotently reconcile the critical ESTORE realm configuration.

Fresh installations are normally created by Keycloak's startup import. This
script also supports safe re-runs: it ensures the realm exists, updates the
confidential estore client, sets the configured client secret, and assigns the
minimal realm-management roles required by the canonical estore-app.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests

ENV_TOKEN = re.compile(r"\$\{(ESTORE_REALM|ESTORE_CLIENT_ID|ESTORE_CLIENT_SECRET)\}")
REALM_UPDATE_FIELDS = {
    "enabled",
    "defaultSignatureAlgorithm",
    "revokeRefreshToken",
    "refreshTokenMaxReuse",
    "accessTokenLifespan",
    "ssoSessionIdleTimeout",
    "ssoSessionMaxLifespan",
    "sslRequired",
    "registrationAllowed",
    "registrationEmailAsUsername",
    "rememberMe",
    "verifyEmail",
    "loginWithEmailAllowed",
    "duplicateEmailsAllowed",
    "resetPasswordAllowed",
    "editUsernameAllowed",
    "bruteForceProtected",
    "permanentLockout",
    "maxFailureWaitSeconds",
    "minimumQuickLoginWaitSeconds",
    "waitIncrementSeconds",
    "quickLoginCheckMilliSeconds",
    "maxDeltaTimeSeconds",
    "failureFactor",
    "browserSecurityHeaders",
    "internationalizationEnabled",
    "userManagedAccessAllowed",
}


class BootstrapError(RuntimeError):
    pass


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise BootstrapError(f"Missing required environment variable: {name}")
    return value


def render(value: Any, values: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: render(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, values) for item in value]
    if isinstance(value, str):
        return ENV_TOKEN.sub(lambda match: values[match.group(1)], value)
    return value


def request(
    method: str,
    url: str,
    *,
    expected: set[int],
    token: str | None = None,
    **kwargs: Any,
) -> requests.Response:
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, url, headers=headers, timeout=15, **kwargs)
    if response.status_code not in expected:
        body = response.text[:1000]
        raise BootstrapError(
            f"{method} {url} returned {response.status_code}; expected {sorted(expected)}: {body}"
        )
    return response


def wait_for_admin_token(
    base_url: str,
    username: str,
    password: str,
    timeout_seconds: int,
) -> str:
    token_url = urljoin(base_url, "realms/master/protocol/openid-connect/token")
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": username,
                    "password": password,
                },
                timeout=10,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                raise BootstrapError("Admin token response did not contain access_token")
            return str(token)
        except Exception as exc:  # bounded startup retry
            last_error = exc
            time.sleep(5)
    raise BootstrapError(f"Timed out obtaining a Keycloak admin token: {last_error}")


def first_client(base_url: str, realm: str, client_id: str, token: str) -> dict[str, Any] | None:
    response = request(
        "GET",
        urljoin(base_url, f"admin/realms/{quote(realm, safe='')}/clients"),
        expected={200},
        token=token,
        params={"clientId": client_id, "first": 0, "max": 2},
    )
    clients = response.json()
    if not isinstance(clients, list):
        raise BootstrapError(f"Unexpected client lookup response for {client_id!r}")
    exact = [item for item in clients if item.get("clientId") == client_id]
    if len(exact) > 1:
        raise BootstrapError(f"Multiple Keycloak clients use clientId={client_id!r}")
    return exact[0] if exact else None


def desired_client(template: dict[str, Any], client_id: str, client_secret: str) -> dict[str, Any]:
    clients = template.get("clients")
    if not isinstance(clients, list):
        raise BootstrapError("Realm template does not contain clients")
    matching = [item for item in clients if item.get("clientId") == client_id]
    if len(matching) != 1:
        raise BootstrapError(f"Realm template must contain exactly one {client_id!r} client")
    client = dict(matching[0])
    client.pop("id", None)
    client["secret"] = client_secret
    attributes = dict(client.get("attributes") or {})
    attributes.pop("client.secret.creation.time", None)
    client["attributes"] = attributes
    return client


def ensure_realm(base_url: str, realm: str, template: dict[str, Any], token: str) -> None:
    realm_url = urljoin(base_url, f"admin/realms/{quote(realm, safe='')}")
    response = requests.get(realm_url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    if response.status_code == 404:
        request(
            "POST",
            urljoin(base_url, "admin/realms"),
            expected={201, 204},
            token=token,
            json=template,
        )
        return
    if response.status_code != 200:
        raise BootstrapError(f"Realm lookup returned {response.status_code}: {response.text[:1000]}")

    update = {key: template[key] for key in REALM_UPDATE_FIELDS if key in template}
    update["realm"] = realm
    request("PUT", realm_url, expected={204}, token=token, json=update)


def ensure_client(
    base_url: str,
    realm: str,
    client_id: str,
    client_secret: str,
    template: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    client = first_client(base_url, realm, client_id, token)
    desired = desired_client(template, client_id, client_secret)
    clients_url = urljoin(base_url, f"admin/realms/{quote(realm, safe='')}/clients")
    if client is None:
        request("POST", clients_url, expected={201, 204}, token=token, json=desired)
        client = first_client(base_url, realm, client_id, token)
        if client is None:
            raise BootstrapError(f"Created client {client_id!r} could not be retrieved")
    else:
        client_uuid = required_field(client, "id", f"client {client_id}")
        update = dict(client)
        update.update(desired)
        update["id"] = client_uuid
        request(
            "PUT",
            urljoin(clients_url + "/", quote(client_uuid, safe="")),
            expected={204},
            token=token,
            json=update,
        )
        client = first_client(base_url, realm, client_id, token)
        if client is None:
            raise BootstrapError(f"Updated client {client_id!r} could not be retrieved")
    return client


def required_field(payload: dict[str, Any], key: str, description: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BootstrapError(f"Missing {key!r} in {description}")
    return value


def ensure_service_account_roles(
    base_url: str,
    realm: str,
    client: dict[str, Any],
    token: str,
) -> None:
    realm_path = f"admin/realms/{quote(realm, safe='')}"
    client_uuid = required_field(client, "id", "estore client")

    service_user = request(
        "GET",
        urljoin(base_url, f"{realm_path}/clients/{quote(client_uuid, safe='')}/service-account-user"),
        expected={200},
        token=token,
    ).json()
    service_user_id = required_field(service_user, "id", "service-account user")

    realm_management = first_client(base_url, realm, "realm-management", token)
    if realm_management is None:
        raise BootstrapError("Built-in realm-management client was not found")
    realm_management_uuid = required_field(realm_management, "id", "realm-management client")

    roles: list[dict[str, Any]] = []
    for role_name in ("view-realm", "manage-users"):
        role = request(
            "GET",
            urljoin(
                base_url,
                f"{realm_path}/clients/{quote(realm_management_uuid, safe='')}/roles/{quote(role_name, safe='')}",
            ),
            expected={200},
            token=token,
        ).json()
        roles.append(role)

    request(
        "POST",
        urljoin(
            base_url,
            f"{realm_path}/users/{quote(service_user_id, safe='')}/role-mappings/clients/{quote(realm_management_uuid, safe='')}",
        ),
        expected={204},
        token=token,
        json=roles,
    )


def main() -> int:
    base_url = required("KC_SERVER_URL").rstrip("/") + "/"
    realm = required("ESTORE_REALM")
    client_id = required("ESTORE_CLIENT_ID")
    client_secret = required("ESTORE_CLIENT_SECRET")
    admin_username = required("KC_BOOTSTRAP_ADMIN_USERNAME")
    admin_password = required("KC_BOOTSTRAP_ADMIN_PASSWORD")
    timeout = int(os.getenv("BOOTSTRAP_TIMEOUT_SECONDS", "600"))

    raw_template = json.loads(
        Path(os.getenv("REALM_TEMPLATE_PATH", "/app/ESTORE-realm-template.json")).read_text(
            encoding="utf-8"
        )
    )
    values = {
        "ESTORE_REALM": realm,
        "ESTORE_CLIENT_ID": client_id,
        "ESTORE_CLIENT_SECRET": client_secret,
    }
    template = render(raw_template, values)
    if not isinstance(template, dict):
        raise BootstrapError("Rendered realm template is not a JSON object")

    token = wait_for_admin_token(base_url, admin_username, admin_password, timeout)
    ensure_realm(base_url, realm, template, token)
    client = ensure_client(base_url, realm, client_id, client_secret, template, token)
    ensure_service_account_roles(base_url, realm, client, token)

    print(
        "PASS: ESTORE realm reconciled; confidential client, configured secret, "
        "and required service-account roles are present."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
