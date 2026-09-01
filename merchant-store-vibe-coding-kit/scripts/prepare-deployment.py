#!/usr/bin/env python3
"""Validate merchant input and generate private platform deployment values.

The helper uses only Python's standard library so an infrastructure agent can
run it immediately after retrieving the public repository. Generated files may
contain secrets, are written mode 0600, and belong in the ignored `.generated/`
directory. The script never prints secret values.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
PLACEHOLDER_RE = re.compile(r"(?:REPLACE_WITH|__REQUIRED|example\.com)", re.IGNORECASE)
BIZ_APP_BASE_URLS = {
    "staging": "https://biz-app.staging.pingbusiness.org",
    "production": "https://biz-app.pingbusiness.org",
}
SUPPORTED_PLATFORMS = {"compose", "northflank", "railway"}
MANAGED_PLATFORMS = {"northflank", "railway"}
DEFAULT_KIT_REPOSITORY_URL = "https://github.com/PingBusiness/PingBusiness"
DEFAULT_KIT_REPOSITORY_BRANCH = "main"
DEFAULT_KIT_REPOSITORY_ROOT_PATH = "/merchant-store-vibe-coding-kit"
KIT_ROOT = Path(__file__).resolve().parents[1]


class InputError(ValueError):
    """Raised for a merchant-supplied value that cannot be deployed safely."""


def require_object(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError(f"{name} must be a JSON object")
    return value


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{key} is required")
    value = value.strip()
    if "\x00" in value or "\n" in value or "\r" in value:
        raise InputError(f"{key} must be one line")
    return value


def optional_string(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise InputError(f"{key} must be a string")
    value = value.strip()
    if "\x00" in value or "\n" in value or "\r" in value:
        raise InputError(f"{key} must be one line")
    return value


def optional_git_sha(value: str, name: str) -> str:
    """Validate an optional exact-commit pin. Empty means 'build the branch head'."""
    value = value.strip()
    if value and not GIT_SHA_RE.fullmatch(value):
        raise InputError(f"{name} must be a 7-40 character hexadecimal Git commit SHA")
    return value


def is_local_hostname(value: str) -> bool:
    """True for hostnames that only ever resolve on the merchant's own machine.

    These have no public DNS and no obtainable ACME certificate, so the edge must
    serve plain HTTP and every advertised URL must use http://. Used by the local
    preview path, never by a real deployment.
    """
    value = value.strip().lower().rstrip(".")
    return value in {"localhost", "127.0.0.1", "::1"} or value.endswith(".localhost")


def validate_hostname(name: str, value: str, allow_local: bool = False) -> str:
    value = value.strip().lower().rstrip(".")
    if allow_local and is_local_hostname(value):
        return value
    if not HOSTNAME_RE.fullmatch(value):
        raise InputError(f"{name} is not a valid public hostname: {value!r}")
    return value


def validate_https_url(name: str, value: str, *, reject_placeholder: bool = True) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise InputError(f"{name} must be an HTTPS URL without embedded credentials")
    if parsed.query or parsed.fragment:
        raise InputError(f"{name} must be a base URL without query or fragment")
    if reject_placeholder and PLACEHOLDER_RE.search(value):
        raise InputError(f"{name} still contains a placeholder")
    return value


def random_secret(bytes_of_entropy: int = 48) -> str:
    return secrets.token_urlsafe(bytes_of_entropy)



def normalize_repo_url(name: str, value: str) -> str:
    value = validate_https_url(name, value, reject_placeholder=False)
    if PLACEHOLDER_RE.search(value):
        raise InputError(f"{name} still contains a publication placeholder")
    return value


def normalize_root_path(value: str, name: str = "rootPath") -> str:
    value = value.strip() or "/"
    if not value.startswith("/"):
        value = "/" + value
    value = re.sub(r"/+", "/", value)
    if ".." in Path(value).parts:
        raise InputError(f"{name} must not contain '..'")
    return value.rstrip("/") or "/"

def join_root_path(root: str, relative: str) -> str:
    root = normalize_root_path(root)
    relative = relative.strip("/")
    return f"/{relative}" if root == "/" else f"{root}/{relative}"


def compose_quote(value: Any) -> str:
    text = str(value)
    if "\x00" in text or "\n" in text or "\r" in text:
        raise InputError("Compose environment values must be one line")
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def write_public(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Merchant deployment JSON")
    parser.add_argument("--output-dir", default=".generated", help="Private output directory")
    parser.add_argument("--repository-url", help="Published public vibe-kit Git URL")
    parser.add_argument("--repository-branch", default=None)
    parser.add_argument("--repository-sha", default=None, help="Exact kit commit SHA to pin builds to (optional)")
    parser.add_argument("--repository-root-path", default=None, help="Path from repository root to this kit")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Generate a local preview deployment: allows storeDomain=localhost, "
        "serves plain HTTP on port 80, and skips ACME. Never use for a real store.",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InputError("Deployment input must be a JSON object")
    if data.get("schemaVersion") != 2:
        raise InputError("schemaVersion must equal 2")

    deployment_name = require_string(data, "deploymentName")
    if not SLUG_RE.fullmatch(deployment_name):
        raise InputError("deploymentName must be a lowercase DNS-safe slug of 3-40 characters")

    platform = require_string(data, "platform").lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise InputError("platform must be one of: " + ", ".join(sorted(SUPPORTED_PLATFORMS)))

    pingbusiness_environment = require_string(data, "pingbusinessEnvironment").lower()
    if pingbusiness_environment not in BIZ_APP_BASE_URLS:
        raise InputError("pingbusinessEnvironment must be staging or production")
    biz_app_base_url = BIZ_APP_BASE_URLS[pingbusiness_environment]

    region = optional_string(data, "region", "ca-central")
    if not region:
        raise InputError("region must not be empty")
    store_domain = validate_hostname(
        "storeDomain", require_string(data, "storeDomain"), allow_local=args.local
    )
    local_mode = args.local and is_local_hostname(store_domain)
    if args.local and not local_mode:
        raise InputError(
            "--local requires storeDomain to be localhost, 127.0.0.1, or a *.localhost name; "
            f"got {store_domain!r}"
        )
    if local_mode and platform != "compose":
        raise InputError("--local is only supported for the compose platform")
    public_scheme = "http" if local_mode else "https"
    public_port = "80" if local_mode else "443"
    store_url = f"{public_scheme}://{store_domain}"
    api_url = f"{store_url}/api"
    keycloak_url = f"{store_url}/auth"

    merchant_identifier = require_string(data, "merchantIdentifier")
    store_identifier = require_string(data, "storeIdentifier")
    merchant_api_key = require_string(data, "merchantApiKey")
    if len(merchant_api_key) < 16 or PLACEHOLDER_RE.search(merchant_api_key):
        raise InputError("merchantApiKey is missing or still a placeholder")
    if PLACEHOLDER_RE.search(merchant_identifier) or PLACEHOLDER_RE.search(store_identifier):
        raise InputError("PingBusiness merchant/store identifiers still contain placeholders")

    keycloak = require_object(data.get("keycloak"), "keycloak")
    if keycloak.get("bruteForceProtection", False) is not False:
        raise InputError("keycloak.bruteForceProtection must remain false for this schema version")
    realm = optional_string(keycloak, "realm", "ESTORE")
    client_id = optional_string(keycloak, "clientId", "estore-app")
    admin_username = optional_string(keycloak, "adminUsername", "admin")
    if not SAFE_ID_RE.fullmatch(realm):
        raise InputError("keycloak.realm contains unsupported characters")
    if not SAFE_ID_RE.fullmatch(client_id):
        raise InputError("keycloak.clientId contains unsupported characters")
    if len(admin_username) < 3:
        raise InputError("keycloak.adminUsername must contain at least 3 characters")
    client_secret = optional_string(keycloak, "clientSecret") or random_secret(48)
    admin_password = optional_string(keycloak, "adminPassword") or random_secret(48)
    if len(client_secret) < 32 or len(admin_password) < 24:
        raise InputError("Keycloak generated/overridden secrets do not meet minimum length")
    database_password = random_secret(48)

    # The remaining platform adapters size PostgreSQL through their own plan
    # arguments (Northflank) or provision it interactively (Railway), so these
    # values are validated for the deployment agent and not emitted anywhere.
    database = require_object(data.get("database"), "database")
    if optional_string(database, "mode", "MANAGED").upper() not in {"MANAGED", "CONTAINER"}:
        raise InputError("database.mode must be MANAGED or CONTAINER")
    if int(database.get("storageGb", 20)) < 10:
        raise InputError("database.storageGb must be at least 10")
    if int(database.get("containerCpuMillicores", 500)) < 250:
        raise InputError("database.containerCpuMillicores must be at least 250")
    if int(database.get("containerMemoryMb", 1024)) < 256:
        raise InputError("database.containerMemoryMb must be at least 256")

    kit_repo = require_object(data.get("kitRepository"), "kitRepository")
    repository_url = args.repository_url or optional_string(kit_repo, "url", DEFAULT_KIT_REPOSITORY_URL) or DEFAULT_KIT_REPOSITORY_URL
    repository_branch = args.repository_branch or optional_string(kit_repo, "branch", DEFAULT_KIT_REPOSITORY_BRANCH)
    repository_sha = optional_git_sha(args.repository_sha or optional_string(kit_repo, "sha", ""), "kitRepository.sha")
    repository_root_path = normalize_root_path(
        args.repository_root_path or optional_string(kit_repo, "rootPath", DEFAULT_KIT_REPOSITORY_ROOT_PATH),
        "kitRepository.rootPath",
    )
    if platform in MANAGED_PLATFORMS:
        if not repository_url:
            raise InputError("A published kit repository URL is required for managed-platform deployment")
        repository_url = normalize_repo_url("kitRepository.url", repository_url)
    elif repository_url:
        repository_url = normalize_repo_url("kitRepository.url", repository_url)

    # The kit's own source/merchant-store tree is a reference implementation to
    # customize, never a deployable storefront. Every deployment therefore has to
    # name a merchant-supplied UI, and there is deliberately no mode that builds
    # the tree shipped in this repository.
    ui = require_object(data.get("uiSource"), "uiSource")
    ui_mode = require_string(ui, "mode").lower()
    if ui_mode not in {"git", "local"}:
        raise InputError("uiSource.mode must be git or local")
    ui_local_path = ""
    ui_dockerfile_path = optional_string(ui, "dockerfilePath", "Dockerfile")
    if ui_dockerfile_path.startswith("/") or ".." in Path(ui_dockerfile_path).parts:
        raise InputError("uiSource.dockerfilePath must be relative and must not contain '..'")
    if ui_mode == "local":
        if platform != "compose":
            raise InputError(
                "uiSource.mode 'local' is only supported for the compose platform. A managed "
                "platform builds from Git, so publish the customized UI to a repository and use "
                "mode 'git'"
            )
        ui_local_path = require_string(ui, "path")
        if not ui_local_path.startswith("/") or ".." in Path(ui_local_path).parts:
            raise InputError("uiSource.path must be an absolute path and must not contain '..'")
        if PLACEHOLDER_RE.search(ui_local_path):
            raise InputError("uiSource.path still contains a placeholder")
        if Path(ui_local_path).resolve() == (KIT_ROOT / "source/merchant-store").resolve():
            raise InputError(
                "uiSource.path is the kit's own source/merchant-store tree, which is a reference "
                "implementation and not a deployable storefront. Customize it first and point "
                "uiSource.path at the customized copy"
            )
        ui_repository_url = ""
        ui_branch = repository_branch
        # A local path is a directory on the target machine, not a checkout, so
        # there is no commit to pin. The path itself is the build context.
        ui_sha = ""
        ui_root_path = "/"
    else:
        ui_repository_url = normalize_repo_url("uiSource.repositoryUrl", require_string(ui, "repositoryUrl"))
        ui_branch = optional_string(ui, "branch", "main")
        ui_sha = optional_git_sha(optional_string(ui, "sha", ""), "uiSource.sha")
        ui_root_path = normalize_root_path(optional_string(ui, "rootPath", "/"))
        if ui_repository_url == repository_url and ui_root_path == join_root_path(repository_root_path, "source/merchant-store"):
            raise InputError(
                "uiSource points at the kit's own source/merchant-store tree, which is a reference "
                "implementation and not a deployable storefront. Publish a customized UI and point "
                "uiSource at it"
            )

    dns = require_object(data.get("dns"), "dns")
    dns_mode = optional_string(dns, "mode", "manual")
    if dns_mode not in {"manual", "provider-api"}:
        raise InputError("dns.mode must be manual or provider-api")
    dns_provider = optional_string(dns, "provider")
    dns_zone = optional_string(dns, "zone")
    dns_api_token = optional_string(dns, "apiToken")
    use_cdn_proxy = bool(dns.get("useCdnProxy", False))
    if dns_mode == "provider-api" and not dns_provider:
        raise InputError("dns.provider is required for provider-api mode")
    if dns_mode == "provider-api" and not dns_api_token:
        raise InputError("dns.apiToken is required for provider-api mode")

    platform_parameters = require_object(data.get("platformParameters"), "platformParameters")
    northflank = require_object(platform_parameters.get("northflank"), "platformParameters.northflank")
    railway = require_object(platform_parameters.get("railway"), "platformParameters.railway")

    store_display_name = optional_string(data, "storeDisplayName")
    store_support_email = optional_string(data, "storeSupportEmail")
    acme_email = optional_string(data, "acmeEmail") or store_support_email or f"admin@{store_domain}"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(stat.S_IRWXU)

    compose_values = {
        "DEPLOYMENT_NAME": deployment_name,
        "PINGBUSINESS_ENVIRONMENT": pingbusiness_environment,
        "STORE_DOMAIN": store_domain,
        # A bare hostname makes Caddy provision ACME. Prefixing the scheme in local
        # mode tells it to serve plain HTTP instead, which is the only thing that
        # can work for a name with no public DNS.
        "STORE_ADDRESS": f"http://{store_domain}" if local_mode else store_domain,
        "PUBLIC_SCHEME": public_scheme,
        "PUBLIC_PORT": public_port,
        "ACME_EMAIL": acme_email,
        "BIZ_APP_BASE_URL": biz_app_base_url,
        "PINGBIZ_MERCHANT_IDENTIFIER": merchant_identifier,
        "PINGBIZ_STORE_IDENTIFIER": store_identifier,
        "PINGBIZ_MERCHANT_API_KEY": merchant_api_key,
        "ESTORE_REALM": realm,
        "ESTORE_CLIENT_ID": client_id,
        "ESTORE_CLIENT_SECRET": client_secret,
        "KC_BOOTSTRAP_ADMIN_USERNAME": admin_username,
        "KC_BOOTSTRAP_ADMIN_PASSWORD": admin_password,
        "KEYCLOAK_DB_NAME": "keycloak_db",
        "KEYCLOAK_DB_USERNAME": "keycloak",
        "KEYCLOAK_DB_PASSWORD": database_password,
        "KEYCLOAK_VERSION": "26.7.0",
        "GUNICORN_WORKERS": "2",
        "GUNICORN_THREADS": "4",
        "GUNICORN_TIMEOUT": "120",
    }
    if ui_mode == "local":
        compose_values["MERCHANT_STORE_BUILD_CONTEXT"] = ui_local_path
        compose_values["MERCHANT_STORE_DOCKERFILE"] = ui_dockerfile_path
    else:
        repo = ui_repository_url[:-4] if ui_repository_url.endswith(".git") else ui_repository_url
        subdir = ui_root_path.strip("/")
        compose_values["MERCHANT_STORE_BUILD_CONTEXT"] = f"{repo}.git#{ui_branch}:{subdir}" if subdir else f"{repo}.git#{ui_branch}"
        compose_values["MERCHANT_STORE_DOCKERFILE"] = ui_dockerfile_path

    compose_env = "\n".join(f"{key}={compose_quote(value)}" for key, value in compose_values.items()) + "\n"
    write_private(output_dir / "compose.env", compose_env)

    if platform == "northflank":
        arguments = {
            "PROJECT_NAME": deployment_name,
            "REGION": region,
            "KIT_REPOSITORY_URL": repository_url,
            "KIT_REPOSITORY_BRANCH": repository_branch,
            "KIT_REPOSITORY_SHA": repository_sha,
            "KIT_REPOSITORY_ROOT_PATH": repository_root_path,
            "UI_REPOSITORY_URL": ui_repository_url,
            "UI_REPOSITORY_BRANCH": ui_branch,
            "UI_REPOSITORY_SHA": ui_sha,
            "UI_DOCKER_WORK_DIR": ui_root_path,
            "UI_DOCKERFILE_PATH": f"{ui_root_path.rstrip('/')}/{ui_dockerfile_path}" if ui_root_path != "/" else f"/{ui_dockerfile_path}",
            "PINGBUSINESS_ENVIRONMENT": pingbusiness_environment,
            "STORE_DOMAIN": store_domain,
            "STORE_DISPLAY_NAME": store_display_name,
            "STORE_SUPPORT_EMAIL": store_support_email,
            "BIZ_APP_BASE_URL": biz_app_base_url,
            "ESTORE_REALM": realm,
            "ESTORE_CLIENT_ID": client_id,
            "KEYCLOAK_ADMIN_USERNAME": admin_username,
            "POSTGRES_VERSION": optional_string(northflank, "postgresVersion", "16-latest"),
            "POSTGRES_STORAGE_MB": str(int(northflank.get("postgresStorageMb", 20480))),
            "POSTGRES_PLAN": optional_string(northflank, "postgresPlan", "nf-compute-50"),
            "KEYCLOAK_PLAN": optional_string(northflank, "keycloakPlan", "nf-compute-100-2"),
            "BOOTSTRAP_PLAN": optional_string(northflank, "bootstrapPlan", "nf-compute-50"),
            "BACKEND_PLAN": optional_string(northflank, "backendPlan", "nf-compute-50"),
            "UI_PLAN": optional_string(northflank, "uiPlan", "nf-compute-20"),
            "EDGE_PLAN": optional_string(northflank, "edgePlan", "nf-compute-20"),
            "BUILD_PLAN": optional_string(northflank, "buildPlan", "nf-compute-400-16"),
        }
        overrides = {
            "KEYCLOAK_ADMIN_PASSWORD": admin_password,
            "ESTORE_CLIENT_SECRET": client_secret,
            "PINGBIZ_MERCHANT_IDENTIFIER": merchant_identifier,
            "PINGBIZ_STORE_IDENTIFIER": store_identifier,
            "PINGBIZ_MERCHANT_API_KEY": merchant_api_key,
        }
        write_public(output_dir / "northflank" / "arguments.json", json_text(arguments))
        write_private(output_dir / "northflank" / "argument-overrides.json", json_text(overrides))

    if platform == "railway":
        railway_public = {
            "projectName": optional_string(railway, "projectName", deployment_name),
            "environmentName": optional_string(railway, "environmentName", "production"),
            "kitRepositoryUrl": repository_url,
            "kitRepositoryBranch": repository_branch,
            "kitRepositoryRootPath": repository_root_path,
            "uiSource": {
                "mode": ui_mode,
                "repositoryUrl": ui_repository_url,
                "branch": ui_branch,
                "rootPath": ui_root_path,
                "dockerfilePath": ui_dockerfile_path,
            },
            "storeDomain": store_domain,
            "pingbusinessEnvironment": pingbusiness_environment,
            "bizAppBaseUrl": biz_app_base_url,
            "services": ["postgres", "keycloak", "keycloak-realm-bootstrap", "estore-app", "merchant-store", "edge"],
            "publicService": optional_string(railway, "edgeServiceName", "edge"),
        }
        railway_secret_variables = {
            "keycloak": {
                "KC_BOOTSTRAP_ADMIN_USERNAME": admin_username,
                "KC_BOOTSTRAP_ADMIN_PASSWORD": admin_password,
                "ESTORE_REALM": realm,
                "ESTORE_CLIENT_ID": client_id,
                "ESTORE_CLIENT_SECRET": client_secret,
            },
            "keycloak-realm-bootstrap": {
                "KC_BOOTSTRAP_ADMIN_USERNAME": admin_username,
                "KC_BOOTSTRAP_ADMIN_PASSWORD": admin_password,
                "ESTORE_REALM": realm,
                "ESTORE_CLIENT_ID": client_id,
                "ESTORE_CLIENT_SECRET": client_secret,
            },
            "estore-app": {
                "BIZ_APP_BASE_URL": biz_app_base_url,
                "PINGBIZ_MERCHANT_IDENTIFIER": merchant_identifier,
                "PINGBIZ_STORE_IDENTIFIER": store_identifier,
                "PINGBIZ_MERCHANT_API_KEY": merchant_api_key,
                "ESTORE_REALM": realm,
                "ESTORE_CLIENT_ID": client_id,
                "ESTORE_CLIENT_SECRET": client_secret,
                # The store root, NOT the /api base. estore-app builds PaymentAsia
                # callbacks as {this}/checkout/return/<id>, and biz-app pins those
                # by exact path, so an /api prefix fails every create-intent with
                # HTTP 400 and no checkout can start. The edge routes the callback
                # paths from the root already; see deployment/edge/routes.caddy.
                "ESTORE_PUBLIC_BASE_URL": store_url,
                "ESTORE_ALLOWED_ORIGINS": store_url,
            },
            "merchant-store": {"ESTORE_APP_PUBLIC_URL": "/api"},
            "edge": {"STORE_DOMAIN": store_domain, "PUBLIC_HOST": store_domain},
        }
        write_public(output_dir / "railway" / "deployment-plan.json", json_text(railway_public))
        write_private(output_dir / "railway" / "service-variables.secret.json", json_text(railway_secret_variables))

    if dns_mode == "provider-api":
        write_private(output_dir / "dns-provider.json", json_text({"provider": dns_provider, "zone": dns_zone, "apiToken": dns_api_token, "useCdnProxy": use_cdn_proxy}))

    summary = {
        "schemaVersion": 1,
        "platform": platform,
        "deploymentName": deployment_name,
        "pingbusinessEnvironment": pingbusiness_environment,
        "bizAppBaseUrl": biz_app_base_url,
        "region": region,
        "storeUrl": store_url,
        "apiBaseUrl": api_url,
        "keycloakBaseUrl": keycloak_url,
        "keycloakAdminUrl": f"{keycloak_url}/admin/",
        "dnsMode": dns_mode,
        "dnsName": store_domain,
        "uiSourceMode": ui_mode,
        "kitRepositoryUrl": repository_url,
        "kitRepositoryBranch": repository_branch,
        "kitRepositorySha": repository_sha,
        "kitRepositoryRootPath": repository_root_path,
        "generatedFilesContainSecrets": True,
        "secretsPrinted": False,
    }
    write_public(output_dir / "deployment-summary.json", json_text(summary))

    print(f"Prepared {platform} deployment files in {output_dir}")
    print(f"PingBusiness environment: {pingbusiness_environment}")
    print(f"Store: {store_url}")
    print("Generated credentials were written only to private files (mode 0600); values were not printed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (InputError, json.JSONDecodeError, OSError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}")
