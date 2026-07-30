import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template_string, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
APP_PORT = int(os.getenv("ESTORE_APP_PORT", "5000"))
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

# This app calls the existing ping business Flask service over the Docker network.
BIZ_APP_BASE_URL = os.getenv("BIZ_APP_BASE_URL", "http://biz-app:5000").rstrip("/")

# PaymentAsia helper access is proxied through biz-app so merchant-hosted
# estore deployments do not need direct network access to pa-app.
ESTORE_PUBLIC_BASE_URL = os.getenv("ESTORE_PUBLIC_BASE_URL", "").rstrip("/")
ESTORE_CHECKOUT_LANG = os.getenv("ESTORE_CHECKOUT_LANG", "")
# Default to the real PaymentAsia hosted checkout flow. This makes /checkout
# contact biz-app's authenticated pa-app proxy for signed hosted-payment fields
# and then auto-submit the browser/iframe to PaymentAsia. Simulated checkout is available only when
# explicitly enabled for isolated local testing.
# Optional CSP frame-ancestors value, for example: "'self' http://localhost:4200".
# Empty by default because many dev deployments serve Angular and estore-app from
# different ports, and the checkout return page is intentionally iframe-friendly.
ESTORE_CHECKOUT_FRAME_ANCESTORS = os.getenv("ESTORE_CHECKOUT_FRAME_ANCESTORS", "").strip()


# The estore deployment belongs to exactly one merchant/store context.
# setup.py prints these values after provisioning the merchant and store.
PINGBIZ_MERCHANT_IDENTIFIER = os.getenv("PINGBIZ_MERCHANT_IDENTIFIER")
PINGBIZ_STORE_IDENTIFIER = os.getenv("PINGBIZ_STORE_IDENTIFIER")

if not PINGBIZ_MERCHANT_IDENTIFIER:
    raise RuntimeError("Missing PINGBIZ_MERCHANT_IDENTIFIER in environment")
if not PINGBIZ_STORE_IDENTIFIER:
    raise RuntimeError("Missing PINGBIZ_STORE_IDENTIFIER in environment")

ESTORE_MERCHANT_ID_INT: Optional[int] = None
ESTORE_STORE_ID_INT: Optional[int] = None

# ESTORE realm: customer identities live here. The service account is used only
# server-side for customer creation/admin updates, never in browser code.
ESTORE_REALM = os.getenv("ESTORE_REALM", "ESTORE")
ESTORE_CLIENT_ID = os.getenv("ESTORE_CLIENT_ID", "estore-app")
ESTORE_CLIENT_SECRET = os.getenv("ESTORE_CLIENT_SECRET")
ESTORE_KC_SERVER_URL = os.getenv("ESTORE_KC_SERVER_URL", os.getenv("KC_SERVER_URL", "http://k-keycloak:8080/auth/")).rstrip("/")
ESTORE_TOKEN_URL = os.getenv(
    "ESTORE_TOKEN_URL",
    f"{ESTORE_KC_SERVER_URL}/realms/{ESTORE_REALM}/protocol/openid-connect/token",
)
ESTORE_LOGOUT_URL = os.getenv(
    "ESTORE_LOGOUT_URL",
    f"{ESTORE_KC_SERVER_URL}/realms/{ESTORE_REALM}/protocol/openid-connect/logout",
)
ESTORE_INTROSPECT_URL = f"{ESTORE_TOKEN_URL}/introspect"
ESTORE_USERS_URL = f"{ESTORE_KC_SERVER_URL}/admin/realms/{ESTORE_REALM}/users"
ESTORE_REALM_ROLES_URL = f"{ESTORE_KC_SERVER_URL}/admin/realms/{ESTORE_REALM}/roles"
ESTORE_CUSTOMER_ROLE = os.getenv("ESTORE_CUSTOMER_ROLE", "").strip()

# PINGBIZ merchant/store scoped API access. Each estore-app deployment is for
# one merchant and one store. Calls to biz-app authenticate with the merchant API
# key and the configured merchant/store identifiers; no shared PingBiz estore
# service secret is required.
PINGBIZ_MERCHANT_API_KEY = os.getenv("PINGBIZ_MERCHANT_API_KEY")

# estore-app exposes only products approved by the PingBusiness review workflow.
PRODUCT_STATE_APPROVED = "A"

# Exact PaymentAsia Standard hosted-payment networks supported by the canonical
# integration guide. UserDefine is not a customer payment method and is excluded.
PAYMENT_ASIA_NETWORKS = (
    "Alipay",
    "Wechat",
    "CUP",
    "CreditCard",
    "Fps",
    "Octopus",
    "PayMe",
)
PAYMENT_ASIA_NETWORK_SET = set(PAYMENT_ASIA_NETWORKS)
HONG_KONG_TZ = ZoneInfo("Asia/Hong_Kong")

if not ESTORE_CLIENT_SECRET:
    raise RuntimeError("Missing ESTORE_CLIENT_SECRET in environment")
if not PINGBIZ_MERCHANT_API_KEY:
    raise RuntimeError("Missing PINGBIZ_MERCHANT_API_KEY in environment")

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__)
if os.getenv("ESTORE_TRUST_PROXY_HEADERS", "true").lower() in {"1", "true", "yes", "y"}:
    # Honor X-Forwarded-Proto/Host so PaymentAsia return_url stays browser-facing
    # and does not fall back to an internal http:// container URL behind a proxy.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()],
)
if DEV_MODE:
    CORS(app)
else:
    CORS(app, resources={r"/*": {"origins": os.getenv("ESTORE_ALLOWED_ORIGINS", "").split(",")}})

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def error(message: str, status: int):
    return jsonify({"error": message}), status


def parse_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer")


def bearer_token_from_request() -> Optional[str]:
    value = request.headers.get("Authorization", "")
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return None


def normalize_username(username: Optional[str]) -> Optional[str]:
    return username.strip().lower() if username else None


def parse_payment_networks(value: Any) -> List[str]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Merchant payment_networks must be a non-empty comma-separated string")
    raw_parts = value.split(",")
    if any(not part.strip() for part in raw_parts):
        raise ValueError("Merchant payment_networks contains an empty entry")
    networks = [part.strip() for part in raw_parts]
    invalid = [network for network in networks if network not in PAYMENT_ASIA_NETWORK_SET]
    if invalid:
        raise ValueError("Merchant payment_networks contains unsupported values: " + ", ".join(invalid))
    if len(set(networks)) != len(networks):
        raise ValueError("Merchant payment_networks contains duplicate values")
    return networks


def get_estore_admin_token() -> str:
    cached = getattr(app, "_estore_admin_token", None)
    cached_exp = getattr(app, "_estore_admin_token_exp", 0)
    now = time.time()
    if cached and cached_exp > now + 30:
        return cached

    response = requests.post(
        ESTORE_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": ESTORE_CLIENT_ID,
            "client_secret": ESTORE_CLIENT_SECRET,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 60))
    app._estore_admin_token = token
    app._estore_admin_token_exp = now + expires_in
    return token


def biz_headers() -> Dict[str, str]:
    return {
        "X-PingBiz-API-Key": PINGBIZ_MERCHANT_API_KEY or "",
        "X-PingBiz-Merchant-Identifier": PINGBIZ_MERCHANT_IDENTIFIER or "",
        "X-PingBiz-Store-Identifier": PINGBIZ_STORE_IDENTIFIER or "",
        "Content-Type": "application/json",
    }


def estore_admin_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {get_estore_admin_token()}",
        "Content-Type": "application/json",
    }


def biz_request(method: str, path: str, *, json_body: Optional[Dict[str, Any]] = None,
                params: Optional[Dict[str, Any]] = None) -> Tuple[Any, int]:
    response = requests.request(
        method,
        f"{BIZ_APP_BASE_URL}{path}",
        headers=biz_headers(),
        json=json_body,
        params=params,
        timeout=20,
    )
    if response.status_code == 204 or not response.text:
        return None, response.status_code
    try:
        return response.json(), response.status_code
    except ValueError:
        return {"raw": response.text}, response.status_code


def ensure_order_item_state_field(payload: Any) -> Any:
    """Guarantee the eStore order-item contract includes the delivery state.

    biz-app is authoritative for the value. This helper only preserves an
    explicit ``state: null`` field when an older or partial upstream payload
    omits it, so storefront clients can render a stable shape.
    """
    if isinstance(payload, dict):
        payload.setdefault("state", None)
    elif isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                row.setdefault("state", None)
    return payload


def proxy_response(payload: Any, status: int):
    if status == 204:
        return ("", 204)
    return jsonify(payload), status


def html_response(html: str, status: int = 200) -> Response:
    response = Response(html, status=status, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    if ESTORE_CHECKOUT_FRAME_ANCESTORS:
        response.headers["Content-Security-Policy"] = f"frame-ancestors {ESTORE_CHECKOUT_FRAME_ANCESTORS}"
    return response


def introspect_customer_token(token: str) -> Dict[str, Any]:
    response = requests.post(
        ESTORE_INTROSPECT_URL,
        data={
            "token": token,
            "client_id": ESTORE_CLIENT_ID,
            "client_secret": ESTORE_CLIENT_SECRET,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("active") is not True:
        raise PermissionError("Customer token is inactive or invalid")
    if not payload.get("sub"):
        raise PermissionError("Customer token missing subject")
    return payload


def customer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = bearer_token_from_request()
        if not token:
            return error("Missing customer bearer token", 401)
        try:
            request.customer_token = introspect_customer_token(token)
            request.customer_subject = request.customer_token["sub"]
        except PermissionError as exc:
            return error("Unauthorized", 401)
        except Exception as exc:
            app.logger.exception("CUSTOMER_TOKEN_VALIDATION_FAILED")
            return error("Customer token validation failed", 401)
        return f(*args, **kwargs)
    return decorated



def require_single_lookup_result(payload: Any, label: str) -> Dict[str, Any]:
    if not isinstance(payload, list):
        raise RuntimeError(f"{label} lookup returned non-list payload: {payload!r}")
    if len(payload) != 1:
        raise RuntimeError(f"{label} lookup expected one result, got {len(payload)}")
    if not isinstance(payload[0], dict):
        raise RuntimeError(f"{label} lookup returned invalid row: {payload[0]!r}")
    return payload[0]


def get_configured_merchant() -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request(
        "GET",
        "/merchants",
        params={"identifier": PINGBIZ_MERCHANT_IDENTIFIER},
    )
    if status >= 400:
        return None, proxy_response(payload, status)
    try:
        merchant = require_single_lookup_result(payload, "merchant")
    except RuntimeError:
        app.logger.exception("INVALID_CONFIGURED_MERCHANT_LOOKUP")
        return None, error("Configured merchant could not be resolved", 502)
    return merchant, None


def get_configured_payment_networks() -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    merchant, err = get_configured_merchant()
    if err:
        return None, err
    if merchant.get("payment_gateway") != "PAYMENT_ASIA":
        return None, error("Merchant is not configured for PaymentAsia checkout", 400)
    try:
        networks = parse_payment_networks(merchant.get("payment_networks"))
    except ValueError as exc:
        app.logger.error("INVALID_MERCHANT_PAYMENT_NETWORKS: %s", exc)
        return None, error("Merchant payment network configuration is invalid", 502)
    return {
        "payment_gateway": merchant.get("payment_gateway"),
        "payment_networks": networks,
    }, None


def resolve_estore_scope_from_config() -> None:
    """Resolve configured merchant/store UUID identifiers through biz-app APIs."""
    global ESTORE_MERCHANT_ID_INT
    global ESTORE_STORE_ID_INT

    merchant_payload, merchant_status = biz_request(
        "GET",
        "/merchants",
        params={"identifier": PINGBIZ_MERCHANT_IDENTIFIER},
    )
    if merchant_status >= 400:
        raise RuntimeError(f"Failed to resolve PINGBIZ_MERCHANT_IDENTIFIER: {merchant_payload!r}")
    merchant = require_single_lookup_result(merchant_payload, "merchant")

    store_payload, store_status = biz_request(
        "GET",
        "/stores",
        params={"identifier": PINGBIZ_STORE_IDENTIFIER},
    )
    if store_status >= 400:
        raise RuntimeError(f"Failed to resolve PINGBIZ_STORE_IDENTIFIER: {store_payload!r}")
    store = require_single_lookup_result(store_payload, "store")

    if store.get("merchant_id") != merchant.get("id"):
        raise RuntimeError("Configured store does not belong to configured merchant")

    ESTORE_MERCHANT_ID_INT = merchant["id"]
    ESTORE_STORE_ID_INT = store["id"]


def get_current_customer() -> Optional[Dict[str, Any]]:
    payload, status = biz_request(
        "GET",
        "/customers",
        params={
            "merchant_id": ESTORE_MERCHANT_ID_INT,
            "store_id": ESTORE_STORE_ID_INT,
            "username": request.customer_subject,
        },
    )
    if status >= 400 or not isinstance(payload, list) or len(payload) == 0:
        return None
    return payload[0]


def require_current_customer() -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    customer = get_current_customer()
    if customer is None:
        return None, error("Customer profile not found for this estore", 404)
    return customer, None


def validate_store_scope(store_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request("GET", f"/store/{store_id}")
    if status == 204 or payload is None:
        return None, error("Store not found", 404)
    if status >= 400:
        return None, proxy_response(payload, status)
    if payload.get("merchant_id") != ESTORE_MERCHANT_ID_INT:
        return None, error("Store is outside this estore merchant scope", 403)
    if payload.get("id") != ESTORE_STORE_ID_INT:
        return None, error("Store is outside this estore store scope", 403)
    return payload, None


def validate_product_scope(product_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request("GET", f"/product/{product_id}")
    if status == 204 or payload is None:
        return None, error("Product not found", 404)
    if status >= 400:
        return None, proxy_response(payload, status)
    if not isinstance(payload, dict):
        return None, error("Invalid product payload from biz-app", 502)
    # biz-app already restricts ESTORE_ROLE to approved products. Keep this
    # local check as defense in depth and as an explicit estore-app contract.
    if payload.get("state") != PRODUCT_STATE_APPROVED:
        return None, error("Product not found", 404)
    _, err = validate_store_scope(parse_int(payload.get("store_id"), "store_id"))
    if err:
        return None, err
    return payload, None


def product_files_for_product(product_id: int) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Any]]:
    payload, status = biz_request("GET", "/files", params={"product_id": product_id})
    if status >= 400:
        return None, proxy_response(payload, status)
    if not isinstance(payload, list):
        return None, error("Invalid files payload from biz-app", 502)
    return payload, None


def attach_product_files(product: Dict[str, Any]) -> Optional[Any]:
    try:
        product_id = parse_int(product.get("id"), "product.id")
    except ValueError as exc:
        return error("Invalid upstream data", 502)

    files, err = product_files_for_product(product_id)
    if err:
        return err
    product["files"] = files or []
    return None


def attach_files_to_products_payload(payload: Any) -> Optional[Any]:
    if not isinstance(payload, list):
        return error("Invalid products payload from biz-app", 502)
    for product in payload:
        if not isinstance(product, dict):
            return error("Invalid product row from biz-app", 502)
        err = attach_product_files(product)
        if err:
            return err
    return None


def validate_product_file_scope(file_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request("GET", f"/file/{file_id}")
    if status == 204 or payload is None:
        return None, error("File not found", 404)
    if status >= 400:
        return None, proxy_response(payload, status)
    if not isinstance(payload, dict):
        return None, error("Invalid file payload from biz-app", 502)

    try:
        product_id = parse_int(payload.get("product_id"), "product_id")
    except ValueError as exc:
        return None, error("Invalid upstream data", 502)

    _, err = validate_product_scope(product_id)
    if err:
        return None, err

    if payload.get("merchant_id") is not None:
        try:
            merchant_id = parse_int(payload.get("merchant_id"), "merchant_id")
        except ValueError as exc:
            return None, error("Invalid upstream data", 502)
        if merchant_id != ESTORE_MERCHANT_ID_INT:
            return None, error("File is outside this estore merchant scope", 403)

    return payload, None


def biz_binary_request(path: str, *, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    headers = dict(biz_headers())
    headers.pop("Content-Type", None)
    return requests.get(
        f"{BIZ_APP_BASE_URL}{path}",
        headers=headers,
        params=params,
        timeout=30,
    )


def proxy_binary_response(response: requests.Response) -> Response:
    excluded_headers = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in excluded_headers
    }
    return Response(response.content, status=response.status_code, headers=headers)


def validate_order_scope(order_id: int, customer: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request("GET", f"/order/{order_id}")
    if status == 204 or payload is None:
        return None, error("Order not found", 404)
    if status >= 400:
        return None, proxy_response(payload, status)
    if payload.get("customer_id") != customer.get("id"):
        return None, error("Order is outside the current customer scope", 403)
    if payload.get("merchant_id") != ESTORE_MERCHANT_ID_INT:
        return None, error("Order is outside this estore merchant scope", 403)
    _, err = validate_store_scope(parse_int(payload.get("store_id"), "store_id"))
    if err:
        return None, err
    return payload, None


def validate_order_item_scope(order_item_id: int, customer: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request("GET", f"/order_item/{order_item_id}")
    if status == 204 or payload is None:
        return None, None, error("Order item not found", 404)
    if status >= 400:
        return None, None, proxy_response(payload, status)
    order, err = validate_order_scope(parse_int(payload.get("order_id"), "order_id"), customer)
    if err:
        return None, None, err
    return payload, order, None


def validate_payment_scope(payment_id: int, customer: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request("GET", f"/payment/{payment_id}")
    if status == 204 or payload is None:
        return None, None, error("Payment not found", 404)
    if status >= 400:
        return None, None, proxy_response(payload, status)
    order, err = validate_order_scope(parse_int(payload.get("order_id"), "order_id"), customer)
    if err:
        return None, None, err
    return payload, order, None


def get_estore_user_id_by_username(username: str) -> Optional[str]:
    response = requests.get(
        ESTORE_USERS_URL,
        headers=estore_admin_headers(),
        params={"username": username, "exact": "true"},
        timeout=15,
    )
    response.raise_for_status()
    users = response.json()
    if not users:
        return None
    return users[0]["id"]


def create_estore_user(data: Dict[str, Any]) -> str:
    username = normalize_username(data.get("username") or data.get("email"))
    password = data.get("password")
    if not username:
        raise ValueError("Missing 'username' or 'email' parameter")
    if not password:
        raise ValueError("Missing 'password' parameter")

    if get_estore_user_id_by_username(username):
        raise FileExistsError("Customer login already exists")

    user_data = {
        "username": username,
        "email": data.get("email", username),
        "enabled": True,
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    if data.get("first_name"):
        user_data["firstName"] = data.get("first_name")
    if data.get("last_name"):
        user_data["lastName"] = data.get("last_name")

    response = requests.post(ESTORE_USERS_URL, headers=estore_admin_headers(), json=user_data, timeout=15)
    if response.status_code not in (201, 204):
        response.raise_for_status()

    user_id = get_estore_user_id_by_username(username)
    if not user_id:
        raise RuntimeError("Created customer user but could not retrieve Keycloak user id")

    if ESTORE_CUSTOMER_ROLE:
        assign_estore_realm_role(user_id, ESTORE_CUSTOMER_ROLE)

    return user_id


def update_estore_user_profile(user_id: str, data: Dict[str, Any]) -> None:
    patch: Dict[str, Any] = {}
    if "email" in data:
        patch["email"] = data.get("email")
    if "first_name" in data:
        patch["firstName"] = data.get("first_name")
    if "last_name" in data:
        patch["lastName"] = data.get("last_name")
    if not patch:
        return
    response = requests.put(f"{ESTORE_USERS_URL}/{user_id}", headers=estore_admin_headers(), json=patch, timeout=15)
    response.raise_for_status()


def get_estore_user_by_id(user_id: str) -> Dict[str, Any]:
    response = requests.get(f"{ESTORE_USERS_URL}/{user_id}", headers=estore_admin_headers(), timeout=15)
    response.raise_for_status()
    return response.json()


def verify_estore_user_password(user_id: str, current_password: str) -> bool:
    user = get_estore_user_by_id(user_id)
    username = user.get("username")
    if not username:
        raise RuntimeError("Keycloak user is missing username")
    response = requests.post(
        ESTORE_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": ESTORE_CLIENT_ID,
            "client_secret": ESTORE_CLIENT_SECRET,
            "username": username,
            "password": current_password,
        },
        timeout=15,
    )
    return response.status_code == 200


def update_estore_user_password(user_id: str, new_password: str) -> None:
    response = requests.put(
        f"{ESTORE_USERS_URL}/{user_id}/reset-password",
        headers=estore_admin_headers(),
        json={"type": "password", "value": new_password, "temporary": False},
        timeout=15,
    )
    response.raise_for_status()


def delete_estore_user(user_id: str) -> None:
    response = requests.delete(f"{ESTORE_USERS_URL}/{user_id}", headers=estore_admin_headers(), timeout=15)
    if response.status_code not in (204, 404):
        response.raise_for_status()


def assign_estore_realm_role(user_id: str, role_name: str) -> None:
    role_response = requests.get(f"{ESTORE_REALM_ROLES_URL}/{role_name}", headers=estore_admin_headers(), timeout=15)
    role_response.raise_for_status()
    response = requests.post(
        f"{ESTORE_USERS_URL}/{user_id}/role-mappings/realm",
        headers=estore_admin_headers(),
        json=[role_response.json()],
        timeout=15,
    )
    response.raise_for_status()


def allowed_customer_update_body(data: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "first_name", "last_name", "details", "shipping_address", "billing_address",
        "email", "phone"
    }
    return {key: value for key, value in data.items() if key in allowed}


# -----------------------------------------------------------------------------
# Checkout helpers
# -----------------------------------------------------------------------------
def public_base_url() -> str:
    if ESTORE_PUBLIC_BASE_URL:
        return ESTORE_PUBLIC_BASE_URL

    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")

    return request.url_root.rstrip("/")


def decimal_from_value(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal number") from exc
    return result


def parse_checkout_cart(data: Dict[str, Any]) -> List[Dict[str, int]]:
    raw_cart = data.get("cart")
    if not isinstance(raw_cart, list) or not raw_cart:
        raise ValueError("cart must be a non-empty list")
    parsed: List[Dict[str, int]] = []
    seen = set()
    for index, item in enumerate(raw_cart):
        if not isinstance(item, dict):
            raise ValueError(f"cart[{index}] must be an object")
        product_id = parse_int(item.get("product_id"), f"cart[{index}].product_id")
        quantity = parse_int(item.get("quantity"), f"cart[{index}].quantity")
        if product_id in seen:
            raise ValueError(f"Duplicate product_id in cart: {product_id}")
        if quantity <= 0:
            raise ValueError(f"cart[{index}].quantity must be greater than zero")
        seen.add(product_id)
        parsed.append({"product_id": product_id, "quantity": quantity})
    return parsed


def get_customer_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()


def product_recurring_plan(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    values = (
        product.get("recurring_frequency"),
        product.get("recurring_intervals"),
        product.get("recurring_total_execution_times"),
    )
    if all(value in (None, "") for value in values):
        return None
    if any(value in (None, "") for value in values):
        raise ValueError(f"Product {product.get('id')} has incomplete recurring terms")

    frequency = str(values[0]).strip().upper()
    if frequency not in {"WEEKLY", "MONTHLY", "YEARLY"}:
        raise ValueError(f"Product {product.get('id')} has invalid recurring_frequency")
    intervals = parse_int(values[1], "product.recurring_intervals")
    total_executions = parse_int(values[2], "product.recurring_total_execution_times")
    if intervals <= 0 or total_executions <= 0:
        raise ValueError(f"Product {product.get('id')} has invalid recurring terms")
    return {
        "recurring_frequency": frequency,
        "recurring_intervals": intervals,
        "recurring_total_execution_times": total_executions,
    }


def next_recurring_start_date() -> str:
    return (datetime.now(HONG_KONG_TZ).date() + timedelta(days=1)).isoformat()


def build_checkout_line(
    item: Dict[str, int],
    *,
    require_recurring: bool,
) -> Tuple[str, Dict[str, Any]]:
    """Build one trusted checkout line from the current approved catalogue."""
    product, err = validate_product_scope(item["product_id"])
    if err:
        raise PermissionError(err)
    if not product:
        raise ValueError(f"Product not found: {item['product_id']}")

    product_currency = str(product.get("currency") or "").upper()
    if not product_currency:
        raise ValueError(f"Product {item['product_id']} is missing currency")

    unit_amount = decimal_from_value(product.get("amount"), f"product {item['product_id']} amount")
    if unit_amount <= 0:
        raise ValueError(f"Product {item['product_id']} amount must be greater than zero")

    recurring_plan = product_recurring_plan(product)
    if require_recurring and recurring_plan is None:
        raise ValueError("Subscribe Now requires a subscription product")
    if not require_recurring and recurring_plan is not None:
        raise ValueError(
            f"Subscription product {item['product_id']} cannot be added to the cart; use Subscribe Now"
        )

    inventory_payload, inventory_status = biz_request(
        "GET",
        "/inventories",
        params={"product_id": item["product_id"]},
    )
    if inventory_status >= 400:
        raise ValueError(f"Could not read inventory for product {item['product_id']}")
    inventory_rows = inventory_payload if isinstance(inventory_payload, list) else []
    available = sum(
        parse_int((row or {}).get("quantity", 0), "inventory.quantity")
        for row in inventory_rows
        if isinstance(row, dict)
    )
    if available < item["quantity"]:
        raise ValueError(
            f"Insufficient inventory for product {item['product_id']}: "
            f"requested {item['quantity']}, available {available}"
        )

    amount = (unit_amount * Decimal(item["quantity"])).quantize(Decimal("0.01"))
    line_item: Dict[str, Any] = {
        "product": product,
        "product_id": item["product_id"],
        "quantity": item["quantity"],
        "unit_amount": unit_amount,
        "amount": amount,
        "is_recurring": recurring_plan is not None,
    }
    if recurring_plan is not None:
        line_item.update(recurring_plan)
        line_item["recurring_start_date"] = next_recurring_start_date()
    return product_currency, line_item


def build_checkout(cart: List[Dict[str, int]]) -> Tuple[str, Decimal, List[Dict[str, Any]]]:
    """Build an ordinary cart. Subscription products must bypass the cart."""
    line_items: List[Dict[str, Any]] = []
    currency: Optional[str] = None
    total = Decimal("0.00")

    for item in cart:
        product_currency, line_item = build_checkout_line(item, require_recurring=False)
        if currency is None:
            currency = product_currency
        elif currency != product_currency:
            raise ValueError("All checkout products must use the same currency")
        total += line_item["amount"]
        line_items.append(line_item)

    if currency is None:
        raise ValueError("cart is empty")
    return currency, total.quantize(Decimal("0.01")), line_items


def build_subscription(product_id: int, quantity: int) -> Tuple[str, Decimal, Dict[str, Any]]:
    """Build exactly one recurring product line for Subscribe Now."""
    currency, line_item = build_checkout_line(
        {"product_id": product_id, "quantity": quantity},
        require_recurring=True,
    )
    if currency != "HKD":
        raise ValueError("PaymentAsia recurring payments support HKD only")
    return currency, line_item["amount"], line_item


def checkout_snapshot_line(line: Dict[str, Any]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "product_id": line["product_id"],
        "quantity": line["quantity"],
        "unit_amount": str(line["unit_amount"]),
        "amount": str(line["amount"]),
    }
    if line.get("is_recurring"):
        snapshot.update({
            "recurring_start_date": line["recurring_start_date"],
            "recurring_frequency": line["recurring_frequency"],
            "recurring_intervals": line["recurring_intervals"],
            "recurring_total_execution_times": line["recurring_total_execution_times"],
        })
    return snapshot


def call_pa_checkout(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    return biz_request("POST", "/pa/checkout", json_body=payload)


def call_recurring_checkout(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    return biz_request("POST", "/recurring/checkout", json_body=payload)


def record_recurring_tokenization(
    intent_identifier: str,
    pa_payload: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request(
        "POST",
        "/recurring/tokenization/record",
        json_body={"intent_identifier": intent_identifier, "payload": pa_payload},
    )
    if status >= 400:
        return None, proxy_response(payload, status)
    return payload if isinstance(payload, dict) else {"payload": payload}, None


def record_recurring_payment(pa_payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, status = biz_request(
        "POST",
        "/recurring/payment/record",
        json_body={"payload": pa_payload},
    )
    if status >= 400:
        return None, proxy_response(payload, status)
    return payload if isinstance(payload, dict) else {"payload": payload}, None


def extract_recurring_redirect_link(payload: Dict[str, Any]) -> str:
    candidates = [
        ((payload.get("normalized_provider_result") or {}).get("redirect_link")
         if isinstance(payload.get("normalized_provider_result"), dict) else None),
        ((payload.get("provider_response") or {}).get("payload", {}).get("redirect_link")
         if isinstance(payload.get("provider_response"), dict)
         and isinstance((payload.get("provider_response") or {}).get("payload"), dict)
         else None),
        payload.get("redirect_link"),
    ]
    for value in candidates:
        if not isinstance(value, str) or not value.strip():
            continue
        parsed = urlparse(value.strip())
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value.strip()
    raise ValueError("PaymentAsia tokenization response is missing a valid redirect link")


def payment_status_label(status: Any) -> str:
    text = str(status or "").strip()
    lowered = text.lower()

    if lowered == "success" or text == "1":
        return "successful"
    if lowered == "fail" or text == "2":
        return "failed"

    return "unknown"


def create_intent(customer_id: int, store_id: int, currency: str, amount: Decimal, status: str, reference: Optional[str], intent_details: Dict[str, Any]) -> Dict[str, Any]:
    body = {
        "customer_id": customer_id,
        "store_id": store_id,
        "currency": currency,
        "amount": str(amount),
        "status": status,
        "reference": reference,
        "intent_details": json.dumps(intent_details, ensure_ascii=False),
    }
    payload, http_status = biz_request("POST", "/intent", json_body=body)
    if http_status >= 400 or not isinstance(payload, dict):
        raise RuntimeError(f"Create intent failed: {payload}")
    return payload


def get_intent_by_identifier(identifier: str) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    payload, http_status = biz_request("GET", "/intents", params={"identifier": identifier})
    if http_status >= 400:
        return None, proxy_response(payload, http_status)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        return None, error("Intent not found", 404)
    return payload[0], None


def record_checkout_payment(intent_identifier: str, pa_payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    """Ask biz-app to verify and record a successful PaymentAsia result.

    biz-app is authoritative for PaymentAsia signature verification, payment
    creation, and order/intent success state. estore-app forwards the callback
    payload directly to biz-app's verified payment-recording endpoint.
    """
    result_body = {
        "intent_identifier": intent_identifier,
        "payload": pa_payload,
    }
    payload, status = biz_request("POST", "/paymentasia/record_payment", json_body=result_body)
    if status >= 400:
        return None, proxy_response(payload, status)

    # biz-app is now authoritative for payment recording and final order-item
    # creation. It finalizes order_items from intent.intent_details["line_items"] inside
    # /paymentasia/record_payment, so estore-app must not create or mutate order
    # items directly after payment.
    return payload if isinstance(payload, dict) else {"payload": payload}, None

CHECKOUT_AUTOSUBMIT_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Opening payment...</title>
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; line-height: 1.45; }
      .card { max-width: 760px; border: 1px solid #ddd; border-radius: 12px; padding: 1.25rem; box-shadow: 0 2px 10px rgba(0,0,0,.06); }
      button { padding: .7rem 1rem; font-size: 1rem; cursor: pointer; }
      .muted { color: #666; }
    </style>
  </head>
  <body data-checkout-id="{{ checkout_id|e }}" data-checkout-reference="{{ checkout_reference|e }}">
    <form method="POST" action="{{ action_url }}" id="payment" accept-charset="utf-8">
      {% for key, value in fields.items() %}
        <input type="hidden" name="{{ key|e }}" value="{{ value|e }}">
      {% endfor %}
      <noscript>
        <div class="card">
          <h1>Open payment</h1>
          <p class="muted">JavaScript is disabled. Continue to the secure payment page.</p>
          <button type="submit">Continue</button>
        </div>
      </noscript>
    </form>
    <script>
      document.getElementById('payment').submit();
    </script>
  </body>
</html>
"""


RECURRING_REDIRECT_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Opening secure card verification...</title>
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; line-height: 1.45; }
      .card { max-width: 760px; border: 1px solid #ddd; border-radius: 12px; padding: 1.25rem; box-shadow: 0 2px 10px rgba(0,0,0,.06); }
      a { display: inline-block; padding: .7rem 1rem; border-radius: .55rem; background: #111827; color: white; text-decoration: none; font-weight: 700; }
      .muted { color: #666; }
    </style>
  </head>
  <body data-checkout-id="{{ checkout_id|e }}">
    <div class="card">
      <h1>Opening secure card verification</h1>
      <p class="muted">You are being redirected to PaymentAsia to verify the card used for this subscription.</p>
      <a href="{{ redirect_link|e }}">Continue</a>
    </div>
    <script>
      window.location.replace({{ redirect_link|tojson }});
    </script>
  </body>
</html>
"""


CHECKOUT_RETURN_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Checkout {{ status_label }}</title>
    <style>
      * { box-sizing: border-box; }
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #111827; background: #f8fafc; }
      .wrap { min-height: 100vh; display: grid; place-items: center; padding: 1rem; }
      .card { width: min(640px, 100%); background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 1.25rem; box-shadow: 0 12px 30px rgba(15,23,42,.08); }
      .eyebrow { margin: 0 0 .25rem; text-transform: uppercase; letter-spacing: .09em; font-size: .78rem; font-weight: 800; color: #b45309; }
      h1 { margin: 0 0 .5rem; font-size: 1.65rem; }
      code { background: #f1f5f9; padding: .15rem .35rem; border-radius: .35rem; }
      .muted { color: #64748b; }
      .detail { display: flex; justify-content: space-between; gap: 1rem; padding: .65rem 0; border-bottom: 1px solid #e5e7eb; }
      .detail:last-of-type { border-bottom: 0; }
      button { border: 0; border-radius: .65rem; background: #f59e0b; color: #111827; font-weight: 800; padding: .75rem 1rem; font-size: 1rem; cursor: pointer; margin-top: 1rem; }
      button:hover { background: #d97706; }
    </style>
  </head>
  <body data-checkout-id="{{ checkout_id|e }}">
    <main class="wrap">
      <section class="card">
        <p class="eyebrow">Checkout update</p>
        <h1>Checkout {{ status_label }}</h1>
        <p>{{ message }}</p>
        {% if order_id %}<div class="detail"><span>Order ID</span><strong><code>{{ order_id }}</code></strong></div>{% endif %}
        {% if payment_reference %}<div class="detail"><span>Payment reference</span><strong><code>{{ payment_reference }}</code></strong></div>{% endif %}
      </section>
    </main>
    <script>
      var checkoutMessage = {
        type: 'PINGBIZ_ESTORE_CHECKOUT_COMPLETE',
        success: {{ success|tojson }},
        statusLabel: {{ status_label|tojson }},
        orderId: {{ order_id|tojson }},
        order_id: {{ order_id|tojson }},
        paymentReference: {{ payment_reference|tojson }},
        payment_reference: {{ payment_reference|tojson }},
        checkoutId: {{ checkout_id|tojson }},
        checkout_id: {{ checkout_id|tojson }}
      };
      function notifyParent() {
        try {
          if (window.parent && window.parent !== window) {
            window.parent.postMessage(checkoutMessage, '*');
          }
        } catch (e) {}
        try {
          if (window.opener) {
            window.opener.postMessage(checkoutMessage, '*');
          }
        } catch (e) {}
      }
      notifyParent();
      window.setTimeout(notifyParent, 500);
      window.setTimeout(notifyParent, 1500);
    </script>
  </body>
</html>
"""


# -----------------------------------------------------------------------------
# Resolve configured merchant/store through biz-app at startup.
# -----------------------------------------------------------------------------
resolve_estore_scope_from_config()
logging.info("Resolved estore scope through biz-app: merchant_id=%s store_id=%s", ESTORE_MERCHANT_ID_INT, ESTORE_STORE_ID_INT)


# -----------------------------------------------------------------------------
# Health/auth convenience
# -----------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "estore-app"}), 200


@app.route("/login", methods=["POST"])
def customer_login():
    """Convenience password-grant login for tests/simple clients.

    Production browser flows can use Keycloak Authorization Code + PKCE directly
    and send the resulting ESTORE access token to this API.
    """
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return error("Missing username or password", 400)
    response = requests.post(
        ESTORE_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": ESTORE_CLIENT_ID,
            "client_secret": ESTORE_CLIENT_SECRET,
            "username": username,
            "password": password,
        },
        timeout=15,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return jsonify(payload), response.status_code


@app.route("/logout", methods=["POST"])
def customer_logout():
    data = request.json or {}
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return error("Missing 'refresh_token' parameter", 400)

    payload = {
        "client_id": ESTORE_CLIENT_ID,
        "client_secret": ESTORE_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(
            ESTORE_LOGOUT_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        app.logger.exception("ESTORE_LOGOUT_FAILED")
        return error("Unauthorized", 401)

    if response.status_code == 204:
        return jsonify({"message": "Logout success"}), 200

    return jsonify({"error": "Unauthorized"}), 401


@app.route("/refresh", methods=["POST"])
def customer_refresh():
    data = request.json or {}
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return error("Missing 'refresh_token' parameter", 400)

    payload = {
        "grant_type": "refresh_token",
        "client_id": ESTORE_CLIENT_ID,
        "client_secret": ESTORE_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(ESTORE_TOKEN_URL, data=payload, timeout=15)
    except requests.RequestException:
        app.logger.exception("ESTORE_REFRESH_FAILED")
        return error("Unauthorized", 401)

    if response.status_code == 200:
        return jsonify(response.json()), 200

    return error("Unauthorized", 401)


@app.route("/user", methods=["GET"])
@customer_required
def read_current_user():
    """Return the logged-in estore customer's user/profile summary.

    This keeps browser clients using the same backend-mediated KeycloakService
    flow as the biz UI: login stores tokens, then GET /user validates the bearer
    token and resolves the customer profile through biz-app.
    """
    requested_username = normalize_username(request.args.get("username"))
    token_username = normalize_username(
        request.customer_token.get("preferred_username")
        or request.customer_token.get("username")
        or request.customer_token.get("email")
    )
    if requested_username and token_username and requested_username != token_username:
        return error("Cannot read another customer user", 403)

    customer, err = require_current_customer()
    if err:
        return err

    user = {
        "sub": request.customer_subject,
        "username": token_username or requested_username or request.customer_subject,
        "email": request.customer_token.get("email") or customer.get("email"),
        "first_name": customer.get("first_name"),
        "last_name": customer.get("last_name"),
        "customer_id": customer.get("id"),
        "customer": customer,
    }
    return jsonify(user), 200


# -----------------------------------------------------------------------------
# Customer CRU
# -----------------------------------------------------------------------------
@app.route("/customer", methods=["POST"])
def set_customer():
    """Create or update the customer profile using the biz-app convention.

    Convention:
      POST /customer without id -> create customer and Keycloak login.
      POST /customer with id    -> update the logged-in customer's own profile.

    Updates are still customer-scoped. The supplied id is only accepted when it
    matches the BCustomers row mapped from the caller's ESTORE token.sub.
    """
    data = request.json or {}

    # Update path: id present, so the caller must be logged in and may update
    # only their own BCustomers row for this estore merchant.
    if "id" in data:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return error("Missing bearer token", 401)
        token = auth_header.split(" ", 1)[1].strip()
        try:
            token_info = introspect_customer_token(token)
        except PermissionError as exc:
            app.logger.warning("CUSTOMER_TOKEN_INTROSPECTION_FAILED: %s", str(exc))
            return error("Unauthorized", 401)
        except Exception:
            app.logger.exception("CUSTOMER_TOKEN_INTROSPECTION_FAILED")
            return error("Token introspection failed", 401)
        if token_info.get("active") is not True:
            return error("Invalid or inactive customer token", 401)

        request.customer_subject = token_info.get("sub")
        request.customer_token = token_info

        customer, err = require_current_customer()
        if err:
            return err

        try:
            requested_id = int(data.get("id"))
        except (TypeError, ValueError):
            return error("id must be an integer", 400)
        if requested_id != customer["id"]:
            return error("Cannot update another customer", 403)

        forbidden = {"identifier", "merchant_id", "store_id", "username", "created_at", "updated_at"}
        if any(field in data for field in forbidden):
            return error("Cannot update identity or system-controlled customer fields", 400)

        body = allowed_customer_update_body(data)
        if not body:
            return error("No updatable customer fields supplied", 400)
        body["id"] = customer["id"]

        payload, status = biz_request("POST", "/customer", json_body=body)
        if status < 400:
            try:
                update_estore_user_profile(request.customer_subject, data)
            except Exception:
                app.logger.exception("UPDATE_ESTORE_USER_PROFILE_FAILED")
                # Business profile update succeeded; return success with a warning.
                return jsonify({"message": "Customer updated; Keycloak profile sync failed"}), 200
        return proxy_response(payload, status)

    # Create path: validate mandatory business-profile fields before creating
    # the Keycloak account, avoiding a create/delete rollback for invalid input.
    billing_address = data.get("billing_address")
    phone = data.get("phone")
    if not isinstance(billing_address, str) or not billing_address.strip():
        return error("Missing 'billing_address' parameter", 400)
    if not isinstance(phone, str) or not phone.strip():
        return error("Missing 'phone' parameter", 400)

    data = dict(data)
    data["billing_address"] = billing_address.strip()
    data["phone"] = phone.strip()

    # No customer token exists yet, so estore-app creates the Keycloak customer
    # user first and then creates the matching BCustomers row.
    try:
        keycloak_user_id = create_estore_user(data)
    except ValueError as exc:
        return error(str(exc), 400)
    except FileExistsError as exc:
        return error(str(exc), 409)
    except Exception as exc:
        app.logger.exception("CREATE_ESTORE_USER_FAILED")
        return error("Create customer login failed", 500)

    biz_body = {
        "merchant_id": ESTORE_MERCHANT_ID_INT,
        "store_id": ESTORE_STORE_ID_INT,
        "username": keycloak_user_id,
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "details": data.get("details"),
        "shipping_address": data.get("shipping_address"),
        "billing_address": data.get("billing_address"),
        "email": data.get("email") or data.get("username"),
        "phone": data.get("phone"),
    }
    if not biz_body["first_name"]:
        delete_estore_user(keycloak_user_id)
        return error("Missing 'first_name' parameter", 400)
    if not biz_body["last_name"]:
        delete_estore_user(keycloak_user_id)
        return error("Missing 'last_name' parameter", 400)

    payload, status = biz_request("POST", "/customer", json_body=biz_body)
    if status >= 400:
        try:
            delete_estore_user(keycloak_user_id)
        except Exception:
            app.logger.exception("ROLLBACK_ESTORE_USER_DELETE_FAILED")
        return proxy_response(payload, status)

    return jsonify({
        "id": payload.get("id") if isinstance(payload, dict) else None,
        "keycloak_user_id": keycloak_user_id,
    }), status


@app.route("/customer", methods=["GET"])
@customer_required
def read_customer():
    customer, err = require_current_customer()
    if err:
        return err
    payload, status = biz_request("GET", f"/customer/{customer['id']}")
    return proxy_response(payload, status)


@app.route("/customer/update_password", methods=["POST"])
@customer_required
def update_password():
    """Update the logged-in customer's own ESTORE Keycloak password.

    Scope comes only from the customer bearer token. Caller-supplied identity
    fields are rejected so one customer cannot target another customer's account.
    """
    customer, err = require_current_customer()
    if err:
        return err

    data = request.json or {}
    forbidden = {"id", "identifier", "merchant_id", "username", "customer_id", "keycloak_user_id", "user_id", "sub"}
    if any(field in data for field in forbidden):
        return error("Cannot supply identity fields for password update", 400)

    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if not current_password:
        return error("Missing 'current_password' parameter", 400)
    if not new_password:
        return error("Missing 'new_password' parameter", 400)
    if not isinstance(new_password, str) or len(new_password) < 8:
        return error("new_password must be at least 8 characters", 400)

    try:
        if not verify_estore_user_password(request.customer_subject, current_password):
            return error("Current password is invalid", 403)
        update_estore_user_password(request.customer_subject, new_password)
    except Exception as exc:
        app.logger.exception("UPDATE_ESTORE_USER_PASSWORD_FAILED")
        return error("Password update failed", 500)

    return jsonify({"message": "Password updated"}), 200


# -----------------------------------------------------------------------------
# Store/catalog read operations
# -----------------------------------------------------------------------------
@app.route("/payment_networks", methods=["GET"])
def get_payment_networks():
    configuration, err = get_configured_payment_networks()
    if err:
        return err
    return jsonify(configuration), 200


@app.route("/store", methods=["GET"])
def get_configured_store():
    if ESTORE_STORE_ID_INT is None:
        return error("PINGBIZ_STORE_IDENTIFIER is not configured", 400)
    return get_store(ESTORE_STORE_ID_INT)


@app.route("/store/<int:store_id>", methods=["GET"])
def get_store(store_id: int):
    _, err = validate_store_scope(store_id)
    if err:
        return err
    payload, status = biz_request("GET", f"/store/{store_id}")
    return proxy_response(payload, status)


@app.route("/products", methods=["GET"])
def get_products():
    params = dict(request.args)
    requested_state = params.get("state")
    if requested_state not in (None, "", PRODUCT_STATE_APPROVED):
        return error("Only approved products are available in estore", 403)
    # Never allow a public caller to broaden the catalogue state filter.
    params["state"] = PRODUCT_STATE_APPROVED
    if ESTORE_STORE_ID_INT is not None:
        requested_store_id = params.get("store_id")
        if requested_store_id is not None:
            try:
                requested_store_id_int = parse_int(requested_store_id, "store_id")
            except ValueError as exc:
                return error(str(exc), 400)
            if requested_store_id_int != ESTORE_STORE_ID_INT:
                return error("store_id is outside this estore store scope", 403)
        params["store_id"] = ESTORE_STORE_ID_INT
    elif "store_id" in params:
        _, err = validate_store_scope(parse_int(params["store_id"], "store_id"))
        if err:
            return err
    else:
        return error("store_id is required", 400)
    payload, status = biz_request("GET", "/products", params=params)
    if status >= 400:
        return proxy_response(payload, status)
    if not isinstance(payload, list):
        return error("Invalid products payload from biz-app", 502)
    if any(not isinstance(product, dict) or product.get("state") != PRODUCT_STATE_APPROVED for product in payload):
        return error("biz-app returned a non-approved product to estore", 502)
    err = attach_files_to_products_payload(payload)
    if err:
        return err
    return jsonify(payload), status


@app.route("/product/<int:product_id>", methods=["GET"])
def get_product(product_id: int):
    payload, err = validate_product_scope(product_id)
    if err:
        return err
    if not isinstance(payload, dict):
        return error("Invalid product payload from biz-app", 502)
    err = attach_product_files(payload)
    if err:
        return err
    return jsonify(payload), 200


@app.route("/inventories", methods=["GET"])
def get_inventories():
    params = dict(request.args)
    product_id_value = params.get("product_id")
    if product_id_value is None:
        return error("Missing 'product_id' parameter", 400)

    try:
        product_id = parse_int(product_id_value, "product_id")
    except ValueError as exc:
        return error(str(exc), 400)

    _, err = validate_product_scope(product_id)
    if err:
        return err

    params["product_id"] = product_id
    payload, status = biz_request("GET", "/inventories", params=params)
    return proxy_response(payload, status)


# Inventory availability is product-scoped for the storefront and is read through
# GET /inventories?product_id=<product_id>, which returns all location rows.
# An empty list means availability is 0.


@app.route("/file/<int:file_id>", methods=["GET"])
def get_product_file(file_id: int):
    payload, err = validate_product_file_scope(file_id)
    if err:
        return err
    return jsonify(payload), 200


@app.route("/image/<int:file_id>", methods=["GET"])
def get_product_image(file_id: int):
    _, err = validate_product_file_scope(file_id)
    if err:
        return err

    try:
        response = biz_binary_request(f"/image/{file_id}")
    except requests.RequestException as exc:
        app.logger.exception("BIZ_IMAGE_RELAY_FAILED")
        return error("Image relay failed", 502)

    return proxy_binary_response(response)


@app.route("/download", methods=["GET"])
def download_product_file():
    file_id_value = request.args.get("file_id")
    if file_id_value is None:
        return error("Missing 'file_id' parameter", 400)

    try:
        file_id = parse_int(file_id_value, "file_id")
    except ValueError as exc:
        return error(str(exc), 400)

    _, err = validate_product_file_scope(file_id)
    if err:
        return err

    try:
        response = biz_binary_request("/download", params={"file_id": file_id})
    except requests.RequestException as exc:
        app.logger.exception("BIZ_DOWNLOAD_RELAY_FAILED")
        return error("Download relay failed", 502)

    return proxy_binary_response(response)


# -----------------------------------------------------------------------------
# Customer-scoped order operations
# -----------------------------------------------------------------------------
@app.route("/orders", methods=["GET"])
@customer_required
def get_orders():
    customer, err = require_current_customer()
    if err:
        return err
    params = dict(request.args)
    params["customer_id"] = customer["id"]
    params["merchant_id"] = ESTORE_MERCHANT_ID_INT
    if ESTORE_STORE_ID_INT is not None:
        params["store_id"] = ESTORE_STORE_ID_INT
    payload, status = biz_request("GET", "/orders", params=params)
    return proxy_response(payload, status)


@app.route("/order/<int:order_id>", methods=["GET"])
@customer_required
def get_order(order_id: int):
    customer, err = require_current_customer()
    if err:
        return err
    _, err = validate_order_scope(order_id, customer)
    if err:
        return err
    payload, status = biz_request("GET", f"/order/{order_id}")
    return proxy_response(payload, status)


# Orders are created by biz-app only after a trusted completion event: a
# verified one-time payment or authenticated acceptance of one subscription schedule.
# Customer-facing POST /order is intentionally not exposed.
# Customer-facing DELETE /order is intentionally not exposed; finalized orders are immutable from estore-ui.


@app.route("/order_items", methods=["GET"])
@customer_required
def get_order_items():
    customer, err = require_current_customer()
    if err:
        return err
    params = dict(request.args)
    params["customer_id"] = customer["id"]
    params["merchant_id"] = ESTORE_MERCHANT_ID_INT
    if ESTORE_STORE_ID_INT is not None:
        params["store_id"] = ESTORE_STORE_ID_INT
    if "order_id" in request.args:
        _, err = validate_order_scope(parse_int(request.args["order_id"], "order_id"), customer)
        if err:
            return err
    if "product_id" in request.args:
        _, err = validate_product_scope(parse_int(request.args["product_id"], "product_id"))
        if err:
            return err
    payload, status = biz_request("GET", "/order_items", params=params)
    if status < 400:
        payload = ensure_order_item_state_field(payload)
    return proxy_response(payload, status)


@app.route("/order_item/<int:order_item_id>", methods=["GET"])
@customer_required
def get_order_item(order_item_id: int):
    customer, err = require_current_customer()
    if err:
        return err
    _, _, err = validate_order_item_scope(order_item_id, customer)
    if err:
        return err
    payload, status = biz_request("GET", f"/order_item/{order_item_id}")
    if status < 400:
        payload = ensure_order_item_state_field(payload)
    return proxy_response(payload, status)


# Order items are finalized by biz-app from the trusted intent snapshot after
# verified one-time payment or authenticated subscription schedule acceptance.
# Customer-facing POST /order_item is intentionally not exposed.


# Customer-facing DELETE /order_item is intentionally not exposed; order items are immutable checkout records.


# -----------------------------------------------------------------------------
# Customer-scoped payment operations
# -----------------------------------------------------------------------------
@app.route("/payments", methods=["GET"])
@customer_required
def get_payments():
    customer, err = require_current_customer()
    if err:
        return err
    params = dict(request.args)
    params["customer_id"] = customer["id"]
    params["merchant_id"] = ESTORE_MERCHANT_ID_INT
    if ESTORE_STORE_ID_INT is not None:
        params["store_id"] = ESTORE_STORE_ID_INT
    if "order_id" in request.args:
        _, err = validate_order_scope(parse_int(request.args["order_id"], "order_id"), customer)
        if err:
            return err
    payload, status = biz_request("GET", "/payments", params=params)
    return proxy_response(payload, status)


@app.route("/payment/<int:payment_id>", methods=["GET"])
@customer_required
def get_payment(payment_id: int):
    customer, err = require_current_customer()
    if err:
        return err
    _, _, err = validate_payment_scope(payment_id, customer)
    if err:
        return err
    payload, status = biz_request("GET", f"/payment/{payment_id}")
    return proxy_response(payload, status)

# Customer-facing POST /payment is intentionally not exposed.
# One-time payment records are created only by verified checkout return/notify
# flows. Subscription schedule acceptance creates an order without a BPayments row.


# -----------------------------------------------------------------------------
# Checkout flow
# -----------------------------------------------------------------------------
def checkout_result_response(
    *,
    status_label: str,
    message: str,
    order_id: Optional[Any] = None,
    payment_reference: Optional[Any] = None,
    checkout_id: Optional[Any] = None,
    success: bool = False,
    http_status: int = 200,
) -> Response:
    return html_response(
        render_template_string(
            CHECKOUT_RETURN_TEMPLATE,
            status_label=status_label,
            message=message,
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=success,
        ),
        status=http_status,
    )


def _parse_intent_json_field(intent: Dict[str, Any], field: str) -> Dict[str, Any]:
    raw = intent.get(field)
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_intent_details(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Return the immutable checkout/cart snapshot supplied at intent creation."""
    return _parse_intent_json_field(intent, "intent_details")


def parse_intent_system_details(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Return trusted biz-app approval, callback, recurring, and audit state."""
    return _parse_intent_json_field(intent, "system_details")


def checkout_reference(intent: Dict[str, Any], details: Dict[str, Any]) -> Optional[str]:
    """Return the storefront checkout reference created before gateway redirect."""
    value = details.get("merchant_reference") or intent.get("reference")
    return str(value) if value not in (None, "") else None


def payment_reference_from_rows(payload: Any) -> Optional[str]:
    """Return the newest non-empty payment reference from a biz-app list payload."""
    if not isinstance(payload, list):
        return None
    rows = [row for row in payload if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
    for row in rows:
        value = row.get("reference")
        if value not in (None, ""):
            return str(value)
    return None


def resolve_checkout_payment_reference(
    intent: Dict[str, Any],
    intent_details: Dict[str, Any],
    system_details: Dict[str, Any],
    *,
    order_id: Optional[Any] = None,
) -> Optional[str]:
    """Resolve the final gateway payment reference with safe fallbacks.

    A successful one-time checkout has a BPayments row. Reading that row is more
    reliable than assuming the intent reference was overwritten with the gateway
    request reference. Before payment completes, return the merchant checkout
    reference so the UI never loses the identifier while it is polling.
    """
    if order_id not in (None, ""):
        try:
            parsed_order_id = parse_int(order_id, "order_id")
            payments, status = biz_request(
                "GET",
                "/payments",
                params={
                    "order_id": parsed_order_id,
                    "customer_id": intent.get("customer_id"),
                    "merchant_id": ESTORE_MERCHANT_ID_INT,
                    "store_id": ESTORE_STORE_ID_INT,
                },
            )
            if status < 400:
                payment_reference = payment_reference_from_rows(payments)
                if payment_reference:
                    return payment_reference
            else:
                app.logger.warning(
                    "CHECKOUT_PAYMENT_REFERENCE_LOOKUP_FAILED checkout=%s order_id=%s status=%s",
                    intent.get("identifier"),
                    parsed_order_id,
                    status,
                )
        except Exception:
            app.logger.exception(
                "CHECKOUT_PAYMENT_REFERENCE_LOOKUP_FAILED checkout=%s order_id=%s",
                intent.get("identifier"),
                order_id,
            )

    for value in (
        system_details.get("request_reference"),
        system_details.get("payment_reference"),
        intent.get("reference"),
        intent_details.get("merchant_reference"),
    ):
        if value not in (None, ""):
            return str(value)
    return None


def get_customer_by_id(customer_id: Any) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    try:
        parsed_id = parse_int(customer_id, "customer_id")
    except ValueError as exc:
        return None, error(str(exc), 400)
    payload, status = biz_request("GET", f"/customer/{parsed_id}")
    if status == 204 or payload is None:
        return None, error("Customer not found", 404)
    if status >= 400:
        return None, proxy_response(payload, status)
    if not isinstance(payload, dict):
        return None, error("Invalid customer response", 502)
    return payload, None


def render_standard_payment_checkout(
    *,
    intent_id: int,
    intent_identifier: str,
    merchant_reference: str,
    currency: str,
    amount: Decimal,
    customer: Dict[str, Any],
    selected_network: str,
    subject: Optional[str] = None,
    lang: Optional[str] = None,
    customer_state: Optional[str] = None,
    customer_country: Optional[str] = None,
    customer_postal_code: Optional[str] = None,
    response_mode: str = "html",
) -> Response:
    base = public_base_url()
    first_name = customer.get("first_name") or "Customer"
    last_name = customer.get("last_name") or "Customer"
    pa_body = {
        "intent_identifier": intent_identifier,
        "merchant_reference": merchant_reference,
        "currency": currency,
        "amount": str(amount.quantize(Decimal("0.01"))),
        "return_url": f"{base}/checkout/return/{intent_identifier}",
        "notify_url": f"{base}/checkout/notify/{intent_identifier}",
        "customer_ip": get_customer_ip(),
        "customer_first_name": first_name,
        "customer_last_name": last_name,
        "customer_address": customer.get("billing_address") or customer.get("shipping_address") or "N/A",
        "customer_phone": customer.get("phone") or "00000000",
        "customer_email": customer.get("email") or "customer@example.com",
        "customer_state": customer_state or "HK",
        "customer_country": customer_country or "HK",
        "customer_postal_code": customer_postal_code or "000000",
        "network": selected_network,
        "generic": False,
        "subject": subject or f"Order {merchant_reference}",
    }
    checkout_lang = lang or ESTORE_CHECKOUT_LANG
    if checkout_lang:
        pa_body["lang"] = checkout_lang

    pa_payload, pa_status = call_pa_checkout(pa_body)
    if pa_status >= 400:
        return proxy_response(pa_payload, pa_status)
    if not isinstance(pa_payload, dict) or not pa_payload.get("action_url") or not isinstance(pa_payload.get("fields"), dict):
        return error("Invalid PaymentAsia checkout response", 502)

    if response_mode == "json":
        # Popup clients should submit this form directly from a real popup
        # document. Returning structured launch data avoids using a top-level
        # blob: URL, whose lifecycle and opener behavior are unreliable after
        # the browser crosses into the hosted PaymentAsia origin.
        return jsonify({
            "checkout_id": intent_identifier,
            "checkout_reference": merchant_reference,
            "action_url": pa_payload["action_url"],
            "fields": pa_payload["fields"],
        }), 200

    return html_response(
        render_template_string(
            CHECKOUT_AUTOSUBMIT_TEMPLATE,
            action_url=pa_payload["action_url"],
            fields=pa_payload["fields"],
            checkout_id=intent_identifier,
            checkout_reference=merchant_reference,
            order_identifier=merchant_reference,
            currency=currency,
            amount=str(amount.quantize(Decimal("0.01"))),
        )
    )


def callback_payload() -> Dict[str, Any]:
    if request.form:
        return request.form.to_dict(flat=True)
    if request.args:
        return request.args.to_dict(flat=True)
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


@app.route("/checkout", methods=["POST"])
@customer_required
def checkout():
    """Start Standard Hosted Payment for a cart of one-time products only."""
    customer, err = require_current_customer()
    if err:
        return err
    data = request.json or {}
    selected_network = data.get("network")
    if not isinstance(selected_network, str) or not selected_network.strip():
        return error("Missing 'network' parameter", 400)
    selected_network = selected_network.strip()

    payment_configuration, configuration_error = get_configured_payment_networks()
    if configuration_error:
        return configuration_error
    allowed_networks = payment_configuration["payment_networks"]
    if selected_network not in allowed_networks:
        return error("Selected payment network is not enabled for this merchant", 403)

    try:
        cart = parse_checkout_cart(data)
        currency, total, line_items = build_checkout(cart)
    except PermissionError as exc:
        return exc.args[0]
    except ValueError as exc:
        return error(str(exc), 400)

    response_mode = str(data.get("response_mode") or "html").strip().lower()
    if response_mode not in {"html", "json"}:
        return error("response_mode must be 'html' or 'json'", 400)

    checkout_line_items = [checkout_snapshot_line(line) for line in line_items]

    # PaymentAsia requires merchant_reference to be unique across payment
    # requests. UUID4 also remains within its 36-character limit.
    merchant_reference = str(uuid.uuid4())
    subject = data.get("subject") or f"Order {merchant_reference}"
    intent_details = {
        "source": "estore_checkout",
        "merchant_reference": merchant_reference,
        "cart": cart,
        "line_items": checkout_line_items,
        "payment_network": selected_network,
        "subject": subject,
        "checkout_options": {
            key: data.get(key)
            for key in (
                "lang",
                "customer_state",
                "customer_country",
                "customer_postal_code",
            )
            if data.get(key) not in (None, "")
        },
        "checkout_kind": "ordinary",
    }
    try:
        intent_payload = create_intent(
            customer_id=parse_int(customer["id"], "customer.id"),
            store_id=ESTORE_STORE_ID_INT,
            currency=currency,
            amount=total,
            status="C",
            reference=merchant_reference,
            intent_details=intent_details,
        )
    except Exception:
        app.logger.exception("CREATE_CHECKOUT_INTENT_FAILED")
        return error("Create checkout intent failed", 500)

    return render_standard_payment_checkout(
        intent_id=parse_int(intent_payload["id"], "intent.id"),
        intent_identifier=str(intent_payload["identifier"]),
        merchant_reference=merchant_reference,
        currency=currency,
        amount=total,
        customer=customer,
        selected_network=selected_network,
        subject=subject,
        lang=data.get("lang"),
        customer_state=data.get("customer_state"),
        customer_country=data.get("customer_country"),
        customer_postal_code=data.get("customer_postal_code"),
        response_mode=response_mode,
    )


@app.route("/subscribe", methods=["POST"])
@customer_required
def subscribe():
    """Start tokenization for exactly one subscription product and quantity."""
    customer, err = require_current_customer()
    if err:
        return err
    data = request.json or {}
    if data.get("product_id") is None:
        return error("Missing 'product_id' parameter", 400)

    try:
        product_id = parse_int(data.get("product_id"), "product_id")
        quantity = parse_int(data.get("quantity", 1), "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        currency, total, line_item = build_subscription(product_id, quantity)
    except PermissionError as exc:
        return exc.args[0]
    except ValueError as exc:
        return error(str(exc), 400)

    payment_configuration, configuration_error = get_configured_payment_networks()
    if configuration_error:
        return configuration_error
    if "CreditCard" not in payment_configuration["payment_networks"]:
        return error("CreditCard payment network is not enabled for this merchant", 403)

    merchant_reference = str(uuid.uuid4())
    product = line_item.get("product") if isinstance(line_item.get("product"), dict) else {}
    subject = data.get("subject") or f"Subscription {product.get('name') or merchant_reference}"
    subscription = {"product_id": product_id, "quantity": quantity}
    intent_details = {
        "source": "estore_subscription",
        "merchant_reference": merchant_reference,
        "subscription": subscription,
        "line_items": [checkout_snapshot_line(line_item)],
        "payment_network": "CreditCard",
        "subject": subject,
        "checkout_kind": "subscription",
    }
    try:
        intent_payload = create_intent(
            customer_id=parse_int(customer["id"], "customer.id"),
            store_id=ESTORE_STORE_ID_INT,
            currency=currency,
            amount=total,
            status="C",
            reference=merchant_reference,
            intent_details=intent_details,
        )
    except Exception:
        app.logger.exception("CREATE_SUBSCRIPTION_INTENT_FAILED")
        return error("Create subscription intent failed", 500)

    intent_identifier = str(intent_payload["identifier"])
    base = public_base_url()
    recurring_body: Dict[str, Any] = {
        "intent_identifier": intent_identifier,
        "customer_ip": get_customer_ip(),
        "return_url": f"{base}/recurring/tokenization/return/{intent_identifier}",
        "notify_url": f"{base}/recurring/tokenization/notify/{intent_identifier}",
        "payment_notify_url": f"{base}/recurring/payment/notify",
        "subject": subject,
    }
    if data.get("token_valid_date") not in (None, ""):
        recurring_body["token_valid_date"] = data.get("token_valid_date")

    recurring_payload, recurring_status = call_recurring_checkout(recurring_body)
    if recurring_status >= 400:
        return proxy_response(recurring_payload, recurring_status)
    if not isinstance(recurring_payload, dict) or recurring_payload.get("accepted") is not True:
        return error("PaymentAsia tokenization request was not accepted", 502)
    try:
        redirect_link = extract_recurring_redirect_link(recurring_payload)
    except ValueError as exc:
        return error(str(exc), 502)

    return html_response(
        render_template_string(
            RECURRING_REDIRECT_TEMPLATE,
            redirect_link=redirect_link,
            checkout_id=intent_identifier,
        )
    )


def render_recurring_tokenization_result(
    checkout_id: str,
    recurring_result: Dict[str, Any],
) -> Response:
    """Render completion after one subscription schedule is accepted."""
    intent, err = get_intent_by_identifier(checkout_id)
    if err:
        return err
    assert intent is not None
    details = parse_intent_details(intent)

    if recurring_result.get("requires_one_time_payment") is True:
        return error("Subscription checkout unexpectedly requested a one-time payment", 502)
    if recurring_result.get("one_time_payment") not in (None, {}):
        return error("Subscription checkout returned unexpected one-time payment details", 502)

    order_items = recurring_result.get("order_items")
    if not isinstance(order_items, list) or len(order_items) != 1:
        return error("Subscription checkout did not create exactly one order item", 502)
    order_item = order_items[0]
    if not isinstance(order_item, dict) or not order_item.get("recurring_merchant_reference"):
        return error("Subscription checkout did not create an active recurring order item", 502)

    order_id = recurring_result.get("order_id") or intent.get("order_id")
    if order_id in (None, ""):
        return error("Subscription checkout did not create an order", 502)
    payment_reference = (
        intent.get("reference")
        or details.get("merchant_reference")
        or recurring_result.get("tokenization_merchant_reference")
    )
    return checkout_result_response(
        status_label="successful",
        message="Your subscription was created successfully.",
        order_id=order_id,
        payment_reference=payment_reference,
        checkout_id=checkout_id,
        success=True,
        http_status=200,
    )


def render_recurring_browser_return_status(checkout_id: str) -> Response:
    """Render a navigation-only recurring return without treating it as a callback.

    PaymentAsia may navigate the customer browser to ``return_url`` without the
    signed tokenization fields. The authoritative signed result is delivered to
    ``notify_url``. This page therefore reports the current durable intent state
    and lets the authenticated storefront continue polling ``/checkout/status``.
    """
    intent, err = get_intent_by_identifier(checkout_id)
    if err:
        return err
    assert intent is not None
    intent_details = parse_intent_details(intent)
    system_details = parse_intent_system_details(intent)
    context = system_details.get("recurring_checkout")
    recurring_state = str(context.get("state") or "") if isinstance(context, dict) else ""
    status = str(intent.get("status") or "")
    order_id = intent.get("order_id")
    payment_reference = intent.get("reference") or intent_details.get("merchant_reference")

    if status == "S":
        return checkout_result_response(
            status_label="successful",
            message="Your subscription was created successfully.",
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=True,
            http_status=200,
        )

    if status == "F":
        return checkout_result_response(
            status_label="failed",
            message="Your subscription could not be created.",
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=False,
            http_status=200,
        )

    if status == "U":
        return checkout_result_response(
            status_label="uncertain",
            message="Your subscription result is being reconciled. Please check your subscriptions shortly.",
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=False,
            http_status=202,
        )

    message = "Card verification returned. Waiting for the secure subscription confirmation."
    if recurring_state == "SCHEDULE_CREATING":
        message = "Card verified. Your subscription schedule is being created."
    return checkout_result_response(
        status_label="processing",
        message=message,
        order_id=order_id,
        payment_reference=payment_reference,
        checkout_id=checkout_id,
        success=False,
        http_status=202,
    )


def render_standard_browser_return_status(checkout_id: str) -> Response:
    """Render the durable one-time checkout state for browser navigation."""
    intent, err = get_intent_by_identifier(checkout_id)
    if err:
        app.logger.warning("CHECKOUT_BROWSER_RETURN_STATUS_UNAVAILABLE checkout_id=%s", checkout_id)
        return checkout_result_response(
            status_label="unavailable",
            message="Checkout status could not be loaded. Return to the store and check Orders shortly.",
            checkout_id=checkout_id,
            success=False,
            http_status=404,
        )
    assert intent is not None
    intent_details = parse_intent_details(intent)
    system_details = parse_intent_system_details(intent)
    status = str(intent.get("status") or "")
    order_id = intent.get("order_id")
    payment_reference = resolve_checkout_payment_reference(
        intent,
        intent_details,
        system_details,
        order_id=order_id,
    )

    if status == "S":
        return checkout_result_response(
            status_label="successful",
            message="Your checkout was successful.",
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=True,
            http_status=200,
        )
    if status == "F":
        return checkout_result_response(
            status_label="failed",
            message="Your payment was not successful.",
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=False,
            http_status=200,
        )
    if status == "U":
        return checkout_result_response(
            status_label="uncertain",
            message="Your payment result is being reconciled. Please check your orders shortly.",
            order_id=order_id,
            payment_reference=payment_reference,
            checkout_id=checkout_id,
            success=False,
            http_status=202,
        )
    return checkout_result_response(
        status_label="processing",
        message="Payment returned. Waiting for the secure payment confirmation.",
        order_id=order_id,
        payment_reference=payment_reference,
        checkout_id=checkout_id,
        success=False,
        http_status=202,
    )


@app.route("/recurring/tokenization/return/<checkout_id>", methods=["GET", "POST"])
def recurring_tokenization_return(checkout_id: str):
    pa_payload = callback_payload()
    # A browser return without a signature is navigation only. Never send an
    # empty or decorative redirect payload to biz-app's strict verifier.
    if not pa_payload.get("sign"):
        return render_recurring_browser_return_status(checkout_id)

    recurring_result, err = record_recurring_tokenization(checkout_id, pa_payload)
    if err:
        return err
    assert recurring_result is not None
    return render_recurring_tokenization_result(checkout_id, recurring_result)


@app.route("/recurring/tokenization/notify/<checkout_id>", methods=["POST"])
def recurring_tokenization_notify(checkout_id: str):
    recurring_result, err = record_recurring_tokenization(checkout_id, callback_payload())
    if err:
        return err
    return jsonify({"ok": True, "checkout": recurring_result}), 200


@app.route("/recurring/payment/notify", methods=["POST"])
def recurring_payment_notify():
    recurring_payment, err = record_recurring_payment(callback_payload())
    if err:
        return err
    return jsonify({"ok": True, "recurring_payment": recurring_payment}), 200


@app.route("/checkout/status/<checkout_id>", methods=["GET"])
@customer_required
def checkout_status(checkout_id: str):
    """Return customer-scoped checkout completion status for the Angular UI.

    This is a fallback for browser/payment-gateway cases where the final
    return page cannot reliably postMessage back to the parent Angular page.
    It does not replace PaymentAsia return/notify processing; it only reports
    the current intent state after those callbacks have updated the backend.
    """
    customer, err = require_current_customer()
    if err:
        return err

    intent, err = get_intent_by_identifier(checkout_id)
    if err:
        return err
    assert intent is not None

    try:
        intent_customer_id = parse_int(intent.get("customer_id"), "intent.customer_id")
        intent_store_id = parse_int(intent.get("store_id"), "intent.store_id")
    except ValueError:
        return error("Invalid checkout scope", 502)
    if intent_customer_id != parse_int(customer.get("id"), "customer.id"):
        return error("Checkout is outside the current customer scope", 403)
    if intent_store_id != ESTORE_STORE_ID_INT:
        return error("Checkout is outside this estore store scope", 403)

    order = None
    if intent.get("order_id") not in (None, ""):
        order, err = validate_order_scope(parse_int(intent.get("order_id"), "intent.order_id"), customer)
        if err:
            return err

    intent_details = parse_intent_details(intent)
    system_details = parse_intent_system_details(intent)
    order_id = order.get("id") if isinstance(order, dict) else intent.get("order_id")
    resolved_payment_reference = resolve_checkout_payment_reference(
        intent,
        intent_details,
        system_details,
        order_id=order_id,
    )
    storefront_checkout_reference = checkout_reference(intent, intent_details)

    status = str(intent.get("status") or "")
    success = status == "S"
    # R means "redirected/processing" in this flow. It is not terminal.
    # The Angular UI must keep waiting until PaymentAsia return/notify updates
    # the intent to S/F/U. Treating R as complete causes a false failure
    # immediately after checkout starts.
    complete = status in {"S", "F", "U"}
    return jsonify({
        "checkout_id": checkout_id,
        "complete": complete,
        "success": success,
        "status": status,
        "order_id": order_id,
        "payment_reference": resolved_payment_reference,
        "checkout_reference": storefront_checkout_reference,
        "paymentasia_status": system_details.get("paymentasia_status"),
        "recurring_checkout_status": (
            system_details.get("recurring_checkout", {}).get("state")
            if isinstance(system_details.get("recurring_checkout"), dict)
            else None
        ),
    }), 200


@app.route("/checkout/return/<checkout_id>", methods=["GET", "POST"])
def checkout_return(checkout_id: str):
    """Render a browser-safe checkout return page in every callback ordering.

    PaymentAsia's signed notify is the durable completion channel. The browser
    return can be unsigned, partial, duplicated, or race with notify. We make a
    best-effort recording attempt when callback-looking fields are present, but
    never expose a verifier/proxy error as the browser page. The durable intent
    state is then rendered as HTML and the Angular storefront confirms it through
    the authenticated checkout-status endpoint.
    """
    pa_payload = callback_payload()
    callback_keys = {
        "status", "merchant_reference", "request_reference", "currency", "amount", "sign"
    }
    if any(key in pa_payload for key in callback_keys):
        _, record_error = record_checkout_payment(checkout_id, pa_payload)
        if record_error:
            app.logger.warning(
                "CHECKOUT_BROWSER_RETURN_RECORD_DEFERRED checkout_id=%s payload_keys=%s",
                checkout_id,
                sorted(str(key) for key in pa_payload.keys()),
            )

    # Always return a visible HTML status page. If notify already completed, this
    # renders success and the final payment reference. Otherwise it renders a
    # processing page that wakes the storefront, whose authenticated polling will
    # observe notify as soon as it commits.
    return render_standard_browser_return_status(checkout_id)


@app.route("/checkout/notify/<checkout_id>", methods=["POST"])
def checkout_notify(checkout_id: str):
    pa_payload = callback_payload()
    payment_record, err = record_checkout_payment(checkout_id, pa_payload)
    if err:
        return err
    return jsonify({"ok": True, "payment": payment_record}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)






