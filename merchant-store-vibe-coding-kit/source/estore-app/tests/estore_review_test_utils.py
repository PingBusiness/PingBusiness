"""Shared helpers for eStore review-framework integration tests."""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

from estore_test_config import biz_admin_credentials, biz_base_url, first_env, load_test_env

load_test_env()


def _env(*names: str, default: Optional[str] = None) -> Optional[str]:
    return first_env(*names, default=default)


class BizReviewClient:
    """Authenticated biz-app client used by eStore integration fixtures."""

    def __init__(self, timeout: int = 30, *, require_admin_credentials: bool = True) -> None:
        username, password = biz_admin_credentials(required=require_admin_credentials)
        self.base_url = biz_base_url()
        self.admin_username = username
        self.admin_password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    def headers(self, *, auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.access_token:
                raise RuntimeError("Authenticated biz request attempted before login")
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | Iterable[int],
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Any:
        expected = {expected_status} if isinstance(expected_status, int) else set(expected_status)
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=self.headers(auth=auth),
            json=json_body,
            params=params,
            timeout=self.timeout,
        )
        try:
            payload: Any = response.json() if response.text else None
        except ValueError:
            payload = response.text
        if response.status_code not in expected:
            raise AssertionError(
                f"{method} {path} expected {sorted(expected)}, got "
                f"{response.status_code}: {payload!r}"
            )
        return payload

    def login_admin(self) -> None:
        if not self.admin_username or not self.admin_password:
            raise RuntimeError("PingBusiness admin credentials are not configured")
        payload = self.request(
            "POST",
            "/login",
            expected_status=200,
            json_body={"username": self.admin_username, "password": self.admin_password},
            auth=False,
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"biz admin login missing access_token: {payload!r}")
        self.access_token = str(token)

    def login_user(self, username: str, password: str) -> "BizReviewClient":
        client = BizReviewClient(timeout=self.timeout, require_admin_credentials=False)
        payload = client.request(
            "POST",
            "/login",
            expected_status=200,
            json_body={"username": username, "password": password},
            auth=False,
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise AssertionError(f"biz manager login missing access_token: {payload!r}")
        client.access_token = str(token)
        return client


def _db_settings() -> Dict[str, str]:
    settings = {
        "host": _env("BIZ_DB_ADMIN_HOST", "DB_HOST", default="p-db") or "p-db",
        "port": _env("BIZ_DB_ADMIN_PORT", "DB_PORT", default="5432") or "5432",
        "dbname": _env("BIZ_DB_ADMIN_NAME", "DB_NAME", "POSTGRES_DB", default="biz_db") or "biz_db",
        "user": _env("BIZ_DB_ADMIN_USER", "BIZ_DB_ADMIN_USERNAME", "DB_USER", "POSTGRES_USER") or "",
        "password": _env("BIZ_DB_ADMIN_PASSWORD", "DB_PASS", "DB_PASSWORD", "POSTGRES_PASSWORD") or "",
    }
    if not settings["user"] or not settings["password"]:
        raise RuntimeError(
            "Direct database cleanup requires BIZ_DB_ADMIN_USER and "
            "BIZ_DB_ADMIN_PASSWORD, or DB_USER/DB_PASS/PostgreSQL fallbacks"
        )
    return settings


def _connect_db():
    settings = _db_settings()
    try:
        import psycopg  # type: ignore

        return psycopg.connect(**settings)
    except ImportError:
        try:
            import psycopg2  # type: ignore

            return psycopg2.connect(**settings)
        except ImportError:
            return None


def _run_psql(sql: str) -> str:
    if shutil.which("psql") is None:
        raise RuntimeError("Neither psycopg/psycopg2 nor psql is available")
    settings = _db_settings()
    env = os.environ.copy()
    env["PGPASSWORD"] = settings["password"]
    command = [
        "psql", "-v", "ON_ERROR_STOP=1", "-A", "-t",
        "-h", settings["host"], "-p", settings["port"],
        "-U", settings["user"], "-d", settings["dbname"],
        "-c", sql,
    ]
    completed = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"psql cleanup failed: {completed.stderr.strip()}")
    return completed.stdout


def delete_products_direct(product_ids: Iterable[int]) -> None:
    """Delete terminal test products and dependent rows directly from PostgreSQL."""
    ids = sorted({int(value) for value in product_ids if value is not None})
    if not ids:
        return
    locations: list[str] = []
    connection = _connect_db()
    if connection is not None:
        placeholders = ",".join(["%s"] * len(ids))
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT location FROM b_files WHERE product_id IN ({placeholders})", ids)
                    locations = [row[0] for row in cursor.fetchall() if row and row[0]]
                    cursor.execute(
                        f"DELETE FROM b_recurring_payments WHERE order_item_id IN "
                        f"(SELECT id FROM b_order_items WHERE product_id IN ({placeholders}))",
                        ids,
                    )
                    cursor.execute(f"DELETE FROM b_order_items WHERE product_id IN ({placeholders})", ids)
                    cursor.execute(f"DELETE FROM b_files WHERE product_id IN ({placeholders})", ids)
                    cursor.execute(f"DELETE FROM b_inventories WHERE product_id IN ({placeholders})", ids)
                    cursor.execute(f"DELETE FROM b_products WHERE id IN ({placeholders})", ids)
                    cursor.execute(f"SELECT COUNT(*) FROM b_products WHERE id IN ({placeholders})", ids)
                    if int(cursor.fetchone()[0]):
                        raise RuntimeError("Direct cleanup left product rows")
        finally:
            connection.close()
    else:
        sql_ids = ",".join(str(value) for value in ids)
        selected = _run_psql(
            f"SELECT location FROM b_files WHERE product_id IN ({sql_ids}) AND location IS NOT NULL;"
        )
        locations = [line.strip() for line in selected.splitlines() if line.strip()]
        _run_psql(
            f"BEGIN; "
            f"DELETE FROM b_recurring_payments WHERE order_item_id IN "
            f"(SELECT id FROM b_order_items WHERE product_id IN ({sql_ids})); "
            f"DELETE FROM b_order_items WHERE product_id IN ({sql_ids}); "
            f"DELETE FROM b_files WHERE product_id IN ({sql_ids}); "
            f"DELETE FROM b_inventories WHERE product_id IN ({sql_ids}); "
            f"DELETE FROM b_products WHERE id IN ({sql_ids}); COMMIT;"
        )

    files_dir = Path(_env("FILES_DIR", default="files") or "files")
    for location in locations:
        try:
            path = files_dir / location
            if path.is_file():
                path.unlink()
        except OSError:
            pass



def delete_orders_direct(order_ids: Iterable[int]) -> None:
    """Delete test orders and dependent delivery rows directly from PostgreSQL."""
    ids = sorted({int(value) for value in order_ids if value is not None})
    if not ids:
        return
    connection = _connect_db()
    if connection is not None:
        placeholders = ",".join(["%s"] * len(ids))
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"DELETE FROM b_payments WHERE order_id IN ({placeholders})", ids)
                    cursor.execute(f"DELETE FROM b_intents WHERE order_id IN ({placeholders})", ids)
                    cursor.execute(
                        f"DELETE FROM b_recurring_payments WHERE order_item_id IN "
                        f"(SELECT id FROM b_order_items WHERE order_id IN ({placeholders}))",
                        ids,
                    )
                    cursor.execute(f"DELETE FROM b_order_items WHERE order_id IN ({placeholders})", ids)
                    cursor.execute(f"DELETE FROM b_orders WHERE id IN ({placeholders})", ids)
                    cursor.execute(f"SELECT COUNT(*) FROM b_orders WHERE id IN ({placeholders})", ids)
                    if int(cursor.fetchone()[0]):
                        raise RuntimeError("Direct cleanup left order rows")
        finally:
            connection.close()
    else:
        sql_ids = ",".join(str(value) for value in ids)
        _run_psql(
            f"BEGIN; "
            f"DELETE FROM b_payments WHERE order_id IN ({sql_ids}); "
            f"DELETE FROM b_intents WHERE order_id IN ({sql_ids}); "
            f"DELETE FROM b_recurring_payments WHERE order_item_id IN "
            f"(SELECT id FROM b_order_items WHERE order_id IN ({sql_ids})); "
            f"DELETE FROM b_order_items WHERE order_id IN ({sql_ids}); "
            f"DELETE FROM b_orders WHERE id IN ({sql_ids}); COMMIT;"
        )

def delete_customers_direct(customer_ids: Iterable[int]) -> None:
    """Delete temporary customer rows when HTTP admin cleanup is unavailable."""
    ids = sorted({int(value) for value in customer_ids if value is not None})
    if not ids:
        return
    connection = _connect_db()
    if connection is not None:
        placeholders = ",".join(["%s"] * len(ids))
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"DELETE FROM b_customers WHERE id IN ({placeholders})", ids)
                    cursor.execute(f"SELECT COUNT(*) FROM b_customers WHERE id IN ({placeholders})", ids)
                    if int(cursor.fetchone()[0]):
                        raise RuntimeError("Direct cleanup left customer rows")
        finally:
            connection.close()
    else:
        sql_ids = ",".join(str(value) for value in ids)
        _run_psql(f"DELETE FROM b_customers WHERE id IN ({sql_ids});")


@dataclass
class ApprovedProductFixture:
    """Temporary approved product with inventory for eStore tests."""

    admin: BizReviewClient
    manager: BizReviewClient
    manager_id: int
    product_id: int
    store_id: int
    merchant_id: int
    quantity: int

    @classmethod
    def create(
        cls,
        estore_url: str,
        timeout: int,
        *,
        quantity: int = 5,
        amount: str = "12.34",
        recurring_frequency: Optional[str] = None,
        recurring_intervals: Optional[int] = None,
        recurring_total_execution_times: Optional[int] = None,
    ) -> "ApprovedProductFixture":
        response = requests.get(f"{estore_url.rstrip('/')}/store", timeout=timeout)
        if response.status_code != 200:
            raise AssertionError(f"GET /store expected 200, got {response.status_code}: {response.text}")
        store = response.json()
        if not isinstance(store.get("id"), int) or not isinstance(store.get("merchant_id"), int):
            raise AssertionError(f"Configured eStore returned invalid store: {store!r}")

        admin = BizReviewClient(timeout)
        admin.login_admin()
        run_id = uuid.uuid4().hex[:12]
        manager_username = f"auto_estore_fixture_manager_{run_id}@example.test"
        manager_password = f"T!{uuid.uuid4().hex}9a"
        manager_row = admin.request(
            "POST", "/user", expected_status=201,
            json_body={
                "username": manager_username,
                "password": manager_password,
                "merchant_id": int(store["merchant_id"]),
                "user_type": "M",
                "details": f"temporary eStore fixture {run_id}",
            },
        )
        manager_id = int(manager_row["id"])
        manager = admin.login_user(manager_username, manager_password)
        product_id: Optional[int] = None
        try:
            product_body: Dict[str, Any] = {
                "store_id": int(store["id"]),
                "name": f"AUTO_ESTORE_FIXTURE_{run_id}",
                "details": "temporary approved eStore integration-test product",
                "description": "temporary approved fixture",
                "identifier": str(uuid.uuid4()),
                "amount": amount,
                "currency": "HKD",
            }
            recurring_values = (
                recurring_frequency,
                recurring_intervals,
                recurring_total_execution_times,
            )
            if any(value is not None for value in recurring_values):
                if not all(value is not None for value in recurring_values):
                    raise ValueError("All recurring fixture fields must be supplied together")
                product_body.update({
                    "recurring_frequency": recurring_frequency,
                    "recurring_intervals": recurring_intervals,
                    "recurring_total_execution_times": recurring_total_execution_times,
                })
            product = manager.request(
                "POST", "/product", expected_status=201,
                json_body=product_body,
            )
            product_id = int(product["id"])
            manager.request(
                "POST", "/submit_product/", expected_status=200,
                json_body={"product_id": product_id},
            )
            admin.request(
                "POST", "/product_state/", expected_status=200,
                json_body={"product_id": product_id, "state": "A", "review_notes": "Automated test fixture"},
            )
            manager.request(
                "POST", "/inventory", expected_status=201,
                json_body={"product_id": product_id, "quantity": quantity, "location": "TEST"},
            )
            return cls(
                admin=admin,
                manager=manager,
                manager_id=manager_id,
                product_id=product_id,
                store_id=int(store["id"]),
                merchant_id=int(store["merchant_id"]),
                quantity=quantity,
            )
        except Exception:
            if product_id is not None:
                try:
                    current = admin.request("GET", f"/product/{product_id}", expected_status=(200, 204, 404))
                    if isinstance(current, dict) and current.get("state") in {"A", "S"}:
                        admin.request(
                            "POST", "/product_state/", expected_status=200,
                            json_body={"product_id": product_id, "state": "D", "review_notes": "Fixture setup rollback"},
                        )
                    admin.request("DELETE", f"/product/{product_id}", expected_status=(200, 404))
                except Exception:
                    try:
                        delete_products_direct([product_id])
                    except Exception:
                        pass
            try:
                admin.request("DELETE", f"/user/{manager_id}", expected_status=(200, 404))
            except Exception:
                pass
            raise

    def cleanup(self) -> None:
        errors: list[str] = []
        try:
            product = self.admin.request("GET", f"/product/{self.product_id}", expected_status=(200, 204, 404))
            if isinstance(product, dict):
                state = product.get("state")
                if state in {"A", "S"}:
                    self.admin.request(
                        "POST", "/product_state/", expected_status=200,
                        json_body={"product_id": self.product_id, "state": "D", "review_notes": "Test cleanup"},
                    )
                    state = "D"
                if state == "D":
                    self.admin.request("DELETE", f"/product/{self.product_id}", expected_status=(200, 404))
                elif state == "R":
                    delete_products_direct([self.product_id])
        except Exception as exc:
            errors.append(f"product {self.product_id}: {exc}")
            try:
                delete_products_direct([self.product_id])
            except Exception as direct_exc:
                errors.append(f"direct product cleanup: {direct_exc}")
        try:
            self.admin.request("DELETE", f"/user/{self.manager_id}", expected_status=(200, 404))
        except Exception as exc:
            errors.append(f"manager {self.manager_id}: {exc}")
        if errors:
            raise AssertionError("Fixture cleanup failed: " + "; ".join(errors))
