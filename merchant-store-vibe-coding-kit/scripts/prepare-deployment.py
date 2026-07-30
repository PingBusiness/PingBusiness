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
PLACEHOLDER_RE = re.compile(r"(?:REPLACE_WITH|__REQUIRED|example\.com)", re.IGNORECASE)
BIZ_APP_BASE_URLS = {
    "staging": "https://biz-app.staging.pingbusiness.org",
    "production": "https://biz-app.pingbusiness.org",
}
SUPPORTED_PLATFORMS = {"compose", "qovery", "northflank", "railway", "coolify"}
MANAGED_PLATFORMS = {"qovery", "northflank", "railway", "coolify"}
DEFAULT_KIT_REPOSITORY_URL = "https://github.com/PingBusiness/PingBusiness"
DEFAULT_KIT_REPOSITORY_BRANCH = "main"
DEFAULT_KIT_REPOSITORY_ROOT_PATH = "/merchant-store-vibe-coding-kit"


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


def validate_hostname(name: str, value: str) -> str:
    value = value.strip().lower().rstrip(".")
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
    parser.add_argument("--repository-root-path", default=None, help="Path from repository root to this kit")
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
    store_domain = validate_hostname("storeDomain", require_string(data, "storeDomain"))
    store_url = f"https://{store_domain}"
    api_url = f"{store_url}/api"
    keycloak_url = f"{store_url}/auth"

    merchant_identifier = require_string(data, "merchantIdentifier")
    store_identifier = require_string(data, "storeIdentifier")
    merchant_api_key = require_string(data, "merchantApiKey")
    if len(merchant_api_key) < 16 or PLACEHOLDER_RE.search(merchant_api_key):
        raise InputError("merchantApiKey is missing or still a placeholder")
    if PLACEHOLDER_RE.search(merchant_identifier) or PLACEHOLDER_RE.search(store_identifier):
        raise InputError("Ping Business merchant/store identifiers still contain placeholders")

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

    database = require_object(data.get("database"), "database")
    database_mode = optional_string(database, "mode", "MANAGED").upper()
    if database_mode not in {"MANAGED", "CONTAINER"}:
        raise InputError("database.mode must be MANAGED or CONTAINER")
    database_version = optional_string(database, "version", "16")
    database_storage_gb = int(database.get("storageGb", 20))
    if database_storage_gb < 10:
        raise InputError("database.storageGb must be at least 10")
    database_instance_type = optional_string(database, "instanceType")
    database_cpu = int(database.get("containerCpuMillicores", 500))
    database_memory = int(database.get("containerMemoryMb", 1024))

    kit_repo = require_object(data.get("kitRepository"), "kitRepository")
    repository_url = args.repository_url or optional_string(kit_repo, "url", DEFAULT_KIT_REPOSITORY_URL) or DEFAULT_KIT_REPOSITORY_URL
    repository_branch = args.repository_branch or optional_string(kit_repo, "branch", DEFAULT_KIT_REPOSITORY_BRANCH)
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

    ui = require_object(data.get("uiSource"), "uiSource")
    ui_mode = optional_string(ui, "mode", "bundled").lower()
    if ui_mode not in {"bundled", "git"}:
        raise InputError("uiSource.mode must be bundled or git")
    if ui_mode == "bundled":
        if not repository_url and platform != "compose":
            raise InputError("Bundled managed-platform UI requires the published kit repository URL")
        ui_repository_url = repository_url or ""
        ui_branch = repository_branch
        ui_root_path = join_root_path(repository_root_path, "source/merchant-store")
        ui_dockerfile_path = "Dockerfile"
    else:
        ui_repository_url = normalize_repo_url("uiSource.repositoryUrl", require_string(ui, "repositoryUrl"))
        ui_branch = optional_string(ui, "branch", "main")
        ui_root_path = normalize_root_path(optional_string(ui, "rootPath", "/"))
        ui_dockerfile_path = optional_string(ui, "dockerfilePath", "Dockerfile")
        if ui_dockerfile_path.startswith("/") or ".." in Path(ui_dockerfile_path).parts:
            raise InputError("uiSource.dockerfilePath must be relative and must not contain '..'")
    qovery_ui_git_token_id = optional_string(ui, "qoveryGitTokenId")

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
    qovery = require_object(platform_parameters.get("qovery"), "platformParameters.qovery")
    northflank = require_object(platform_parameters.get("northflank"), "platformParameters.northflank")
    railway = require_object(platform_parameters.get("railway"), "platformParameters.railway")
    coolify = require_object(platform_parameters.get("coolify"), "platformParameters.coolify")

    store_display_name = optional_string(data, "storeDisplayName")
    store_support_email = optional_string(data, "storeSupportEmail")
    acme_email = optional_string(data, "acmeEmail") or store_support_email or f"admin@{store_domain}"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(stat.S_IRWXU)

    compose_values = {
        "DEPLOYMENT_NAME": deployment_name,
        "PINGBUSINESS_ENVIRONMENT": pingbusiness_environment,
        "STORE_DOMAIN": store_domain,
        "STORE_ADDRESS": store_domain,
        "PUBLIC_SCHEME": "https",
        "PUBLIC_PORT": "443",
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
    if ui_mode == "bundled":
        compose_values["MERCHANT_STORE_BUILD_CONTEXT"] = "../../source/merchant-store"
        compose_values["MERCHANT_STORE_DOCKERFILE"] = "Dockerfile"
    else:
        repo = ui_repository_url[:-4] if ui_repository_url.endswith(".git") else ui_repository_url
        subdir = ui_root_path.strip("/")
        compose_values["MERCHANT_STORE_BUILD_CONTEXT"] = f"{repo}.git#{ui_branch}:{subdir}" if subdir else f"{repo}.git#{ui_branch}"
        compose_values["MERCHANT_STORE_DOCKERFILE"] = ui_dockerfile_path

    compose_env = "\n".join(f"{key}={compose_quote(value)}" for key, value in compose_values.items()) + "\n"
    write_private(output_dir / "compose.env", compose_env)

    if platform == "qovery":
        organization_id = optional_string(qovery, "organizationId")
        cluster_id = optional_string(qovery, "clusterId")
        if not organization_id or not cluster_id:
            raise InputError("platformParameters.qovery.organizationId and clusterId are required; the Qovery agent should discover them or create/select a cluster first")
        if database_mode == "MANAGED" and not database_instance_type:
            raise InputError("database.instanceType is required for a Qovery MANAGED database and must match the selected cloud provider")
        qovery_values = {
            "qovery_organization_id": organization_id,
            "qovery_cluster_id": cluster_id,
            "project_name": optional_string(qovery, "projectName", deployment_name),
            "environment_name": optional_string(qovery, "environmentName", "production"),
            "kit_repository_url": repository_url,
            "kit_repository_branch": repository_branch,
            "kit_repository_root_path": repository_root_path,
            "ui_repository_url": ui_repository_url,
            "ui_repository_branch": ui_branch,
            "ui_repository_root_path": ui_root_path,
            "ui_dockerfile_path": ui_dockerfile_path,
            "ui_git_token_id": qovery_ui_git_token_id,
            "pingbusiness_environment": pingbusiness_environment,
            "store_domain": store_domain,
            "store_display_name": store_display_name,
            "store_support_email": store_support_email,
            "biz_app_base_url": biz_app_base_url,
            "pingbiz_merchant_identifier": merchant_identifier,
            "pingbiz_store_identifier": store_identifier,
            "pingbiz_merchant_api_key": merchant_api_key,
            "estore_realm": realm,
            "estore_client_id": client_id,
            "estore_client_secret": client_secret,
            "keycloak_admin_username": admin_username,
            "keycloak_admin_password": admin_password,
            "database_mode": database_mode,
            "database_version": database_version,
            "database_storage_gb": database_storage_gb,
            "database_instance_type": database_instance_type,
            "database_cpu_millicores": database_cpu,
            "database_memory_mb": database_memory,
            "use_cdn": use_cdn_proxy,
        }
        write_private(output_dir / "qovery" / "terraform.tfvars.json", json_text(qovery_values))

    if platform == "northflank":
        arguments = {
            "PROJECT_NAME": deployment_name,
            "REGION": region,
            "KIT_REPOSITORY_URL": repository_url,
            "KIT_REPOSITORY_BRANCH": repository_branch,
            "KIT_REPOSITORY_ROOT_PATH": repository_root_path,
            "UI_REPOSITORY_URL": ui_repository_url,
            "UI_REPOSITORY_BRANCH": ui_branch,
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
                "ESTORE_PUBLIC_BASE_URL": api_url,
                "ESTORE_ALLOWED_ORIGINS": store_url,
            },
            "merchant-store": {"ESTORE_APP_PUBLIC_URL": "/api"},
            "edge": {"STORE_DOMAIN": store_domain, "PUBLIC_HOST": store_domain},
        }
        write_public(output_dir / "railway" / "deployment-plan.json", json_text(railway_public))
        write_private(output_dir / "railway" / "service-variables.secret.json", json_text(railway_secret_variables))

    if platform == "coolify":
        coolify_public = {
            "applicationName": optional_string(coolify, "applicationName", deployment_name),
            "projectUuid": optional_string(coolify, "projectUuid"),
            "serverUuid": optional_string(coolify, "serverUuid"),
            "environmentName": optional_string(coolify, "environmentName", "production"),
            "destinationUuid": optional_string(coolify, "destinationUuid"),
            "instantDeploy": bool(coolify.get("instantDeploy", False)),
            "kitRepositoryUrl": repository_url,
            "kitRepositoryBranch": repository_branch,
            "kitRepositoryRootPath": repository_root_path,
            "composeFilePath": join_root_path(repository_root_path, "deployment/coolify/compose.yaml"),
            "storeDomain": store_domain,
            "pingbusinessEnvironment": pingbusiness_environment,
            "bizAppBaseUrl": biz_app_base_url,
        }
        coolify_env = dict(compose_values)
        coolify_env.update({
            "MERCHANT_STORE_BUILD_CONTEXT": "../../source/merchant-store" if ui_mode == "bundled" else compose_values["MERCHANT_STORE_BUILD_CONTEXT"],
            "MERCHANT_STORE_DOCKERFILE": ui_dockerfile_path,
        })
        write_public(output_dir / "coolify" / "deployment-plan.json", json_text(coolify_public))
        write_private(output_dir / "coolify" / "environment.secret.env", "\n".join(f"{k}={v}" for k, v in sorted(coolify_env.items())) + "\n")
        api_body = {
            "project_uuid": optional_string(coolify, "projectUuid"),
            "server_uuid": optional_string(coolify, "serverUuid"),
            "environment_name": optional_string(coolify, "environmentName", "production"),
            "destination_uuid": optional_string(coolify, "destinationUuid"),
            "name": optional_string(coolify, "applicationName", deployment_name),
            "description": f"Ping Business merchant store for {store_domain}",
            "instant_deploy": bool(coolify.get("instantDeploy", False)),
            "connect_to_docker_network": True,
            "docker_compose_raw": f"<load {join_root_path(repository_root_path, 'deployment/coolify/compose.yaml')} from {repository_url}@{repository_branch}>",
        }
        write_private(output_dir / "coolify" / "api-request-body.secret.json", json_text(api_body))

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
        "kitRepositoryRootPath": repository_root_path,
        "generatedFilesContainSecrets": True,
        "secretsPrinted": False,
    }
    write_public(output_dir / "deployment-summary.json", json_text(summary))

    print(f"Prepared {platform} deployment files in {output_dir}")
    print(f"Ping Business environment: {pingbusiness_environment}")
    print(f"Store: {store_url}")
    print("Generated credentials were written only to private files (mode 0600); values were not printed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (InputError, json.JSONDecodeError, OSError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}")
