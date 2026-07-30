"""Shared environment loading and configuration for estore integration tests."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv


def load_test_env() -> None:
    """Load .env from common deployment/test locations without overriding exports."""
    explicit = os.getenv("ESTORE_TEST_DOTENV") or os.getenv("DOTENV_PATH")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))

    here = Path(__file__).resolve()
    candidates.extend(parent / ".env" for parent in [Path.cwd(), *here.parents])
    candidates.extend(
        Path(path)
        for path in (
            "/app/app/estore/tests/.env",
        )
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            load_dotenv(candidate, override=False)


load_test_env()


def first_env(*names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def estore_base_url() -> str:
    return (first_env("ESTORE_APP_BASE_URL", default="http://estore-app:5000") or "http://estore-app:5000").rstrip("/")


def biz_base_url() -> str:
    return (
        first_env("BIZ_APP_BASE_URL", "BIZ_BASE_URL", default="http://biz-app:5000")
        or "http://biz-app:5000"
    ).rstrip("/")


def biz_admin_credentials(required: bool = True) -> Tuple[Optional[str], Optional[str]]:
    username = first_env(
        "BIZ_ADMIN_USERNAME",
        "BIZ_USERNAME",
        "PINGBIZ_ADMIN_USERNAME",
        "PINGBIZ_USERNAME",
        "PINGBIZ_TEST_ADMIN_USERNAME",
        "TEST_BIZ_ADMIN_USERNAME",
        "ADMIN_USERNAME",
    )
    password = first_env(
        "BIZ_ADMIN_PASSWORD",
        "BIZ_PASSWORD",
        "PINGBIZ_ADMIN_PASSWORD",
        "PINGBIZ_PASSWORD",
        "PINGBIZ_TEST_ADMIN_PASSWORD",
        "TEST_BIZ_ADMIN_PASSWORD",
        "ADMIN_PASSWORD",
    )
    if required and (not username or not password):
        raise RuntimeError(
            "Missing PingBusiness admin credentials. Set BIZ_ADMIN_USERNAME and "
            "BIZ_ADMIN_PASSWORD (or BIZ_USERNAME/BIZ_PASSWORD) in the test .env. "
            "The biz-app URL defaults to http://biz-app:5000."
        )
    return username, password
