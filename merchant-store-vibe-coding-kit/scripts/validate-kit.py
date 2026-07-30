#!/usr/bin/env python3
"""Deterministic static validation for the Ping Business merchant-store vibe kit."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASHES = {
    "source/estore-app/app.py": "15aa437974087b5e3e4a8333f40863bc4529e6c90c9a0b62416dac987f2bfe84",
    "source/estore-app/requirements.txt": "231ace13723c7d76f6cb1ace0421deb3d776944dd89bb329ff0b568dad8a5030",
    "keycloak/ESTORE-realm-template.json": "7ea8632c8f2d7dc360ef99ad1ee3a8a21c607e3cb6ac04cf7fdf3c2ddf9dd3b1",
}
REQUIRED_FILES = [
    "README.md", "AGENTS.md", "CLAUDE.md", "llms.txt", "SOURCE_MANIFEST.md", "SOURCE_PATCHES.md", "VALIDATION_REPORT.md",
    "LICENSE", "NOTICE", "TRADEMARKS.md", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "PUBLISHING.md", "kit-metadata.json",
    "design/DESIGN_AGENT.md", "prompts/DESIGN_PROMPT.md",
    "deployment/DEPLOY_AGENT.md", "prompts/DEPLOY_PROMPT.md",
    "deployment/deployment-input.schema.json", "deployment/deployment-output.schema.json",
    "deployment/compose/compose.yaml", "deployment/edge/routes.caddy",
    "deployment/qovery/main.tf", "deployment/northflank/template.json",
    "deployment/railway/README.md", "deployment/railway/service-map.json", "deployment/railway/variables.example.json",
    "deployment/coolify/README.md", "deployment/coolify/compose.yaml", "deployment/coolify/env.example",
    "docs/PLATFORM_SUPPORT.md", "website/pingbusiness-store-launcher.html", "website/README.md",
    "github/merchant-store-vibe-kit-validate.yml", "github/merchant-store-vibe-kit.instructions.md",
    "keycloak/Dockerfile", "keycloak/realm-bootstrap/bootstrap_realm.py",
    "source/merchant-store/Dockerfile", "source/merchant-store/docker-entrypoint.sh",
    "source/merchant-store/LICENSE", "source/merchant-store/NOTICE",
    "source/estore-app/LICENSE", "source/estore-app/NOTICE",
]
PUBLIC_REPOSITORY_URL = "https://github.com/PingBusiness/PingBusiness"
PUBLIC_KIT_ROOT_PATH = "/merchant-store-vibe-coding-kit"
PUBLIC_KIT_TREE_URL = "https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit"
PUBLIC_AGENT_ENTRYPOINT_URL = "https://raw.githubusercontent.com/PingBusiness/PingBusiness/main/merchant-store-vibe-coding-kit/AGENTS.md"
PUBLIC_RELEASE_ASSET_URL = "https://github.com/PingBusiness/PingBusiness/releases/latest/download/pingbusiness-merchant-store-vibe-coding-kit.zip"

BIZ_APP_URLS = {
    "staging": "https://biz-app.staging.pingbusiness.org",
    "production": "https://biz-app.pingbusiness.org",
}

errors: list[str] = []
warnings: list[str] = []
passes: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


def ok(message: str) -> None:
    passes.append(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def walk_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item)


def validate_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail("missing required files: " + ", ".join(missing))
    else:
        ok("required design, deployment, source, platform, website, and test files are present")


def validate_hashes() -> None:
    for rel, expected in EXPECTED_HASHES.items():
        path = ROOT / rel
        if not path.is_file():
            fail(f"canonical file missing: {rel}")
            continue
        actual = sha256(path)
        if actual != expected:
            fail(f"canonical integrity failure for {rel}: {actual} != {expected}")
        else:
            ok(f"canonical integrity preserved: {rel}")


def validate_input_schema() -> None:
    schema = json.loads(text("deployment/deployment-input.schema.json"))
    required = set(schema.get("required", []))
    if schema.get("properties", {}).get("schemaVersion", {}).get("const") != 2:
        fail("deployment input schema must be schemaVersion 2")
    if "pingbusinessEnvironment" not in required:
        fail("deployment input schema must require pingbusinessEnvironment")
    if "bizAppBaseUrl" in schema.get("properties", {}):
        fail("deployment input schema must not expose merchant-facing bizAppBaseUrl")
    platform_enum = set(schema.get("properties", {}).get("platform", {}).get("enum", []))
    expected = {"compose", "qovery", "northflank", "railway", "coolify"}
    if platform_enum != expected:
        fail(f"platform enum mismatch: {platform_enum}")
    env_enum = set(schema.get("properties", {}).get("pingbusinessEnvironment", {}).get("enum", []))
    if env_enum != {"staging", "production"}:
        fail("pingbusinessEnvironment must be exactly staging/production")
    kit_repo = schema.get("properties", {}).get("kitRepository", {}).get("properties", {})
    if kit_repo.get("url", {}).get("default") != PUBLIC_REPOSITORY_URL:
        fail("kitRepository.url must default to the canonical PingBusiness monorepo")
    if kit_repo.get("rootPath", {}).get("default") != PUBLIC_KIT_ROOT_PATH:
        fail("kitRepository.rootPath must default to the published kit directory")
    script = text("scripts/prepare-deployment.py")
    for environment, url in BIZ_APP_URLS.items():
        if f'"{environment}": "{url}"' not in script:
            fail(f"prepare-deployment.py missing {environment} biz-app mapping")
    if PUBLIC_REPOSITORY_URL not in script or PUBLIC_KIT_ROOT_PATH not in script:
        fail("deployment generator is not configured for the public monorepo path")
    if "BIZ_APP_BASE_URLS" not in script or "bizAppBaseUrl" in text("deployment/deployment-input.schema.json"):
        fail("deployment generator must derive BIZ_APP_BASE_URL internally")
    ok("deployment schema and generator use staging/production environment mapping")


def validate_realm() -> None:
    realm = json.loads(text("keycloak/ESTORE-realm-template.json"))
    if realm.get("bruteForceProtected") is not False:
        fail("ESTORE realm brute-force protection must remain disabled")
    if realm.get("permanentLockout") is not False:
        fail("ESTORE realm permanent lockout must remain disabled")
    rendered = json.dumps(realm)
    if "**********" in rendered:
        fail("masked export secret remains in portable realm template")
    if "${ESTORE_CLIENT_SECRET}" not in rendered:
        fail("portable realm template does not contain ESTORE_CLIENT_SECRET placeholder")
    clients = realm.get("clients", [])
    clients = [c for c in clients if c.get("clientId") == "${ESTORE_CLIENT_ID}"]
    if len(clients) != 1:
        fail("portable realm must contain exactly one parameterized estore client")
    elif not (clients[0].get("directAccessGrantsEnabled") and clients[0].get("serviceAccountsEnabled")):
        fail("estore client must enable direct grants and service accounts")
    if realm.get("smtpServer") not in ({}, None):
        fail("portable realm unexpectedly contains SMTP configuration")
    if realm.get("identityProviders"):
        fail("portable realm unexpectedly contains identity providers")
    ok("portable realm contains no live secret and preserves the agreed lockout decision")


def validate_ui() -> None:
    ui_root = ROOT / "source/merchant-store"
    if any(path.name == "estore-ui" for path in ROOT.rglob("estore-ui")):
        fail("obsolete estore-ui directory is present")
    config = text("source/merchant-store/src/app/app.configs.ts")
    index = text("source/merchant-store/src/index.html")
    entrypoint = text("source/merchant-store/docker-entrypoint.sh")
    if "__PINGBUSINESS_CONFIG__" not in config or "runtime-config.js" not in index:
        fail("merchant UI is not runtime configurable")
    if "ESTORE_APP_PUBLIC_URL:-/api" not in entrypoint:
        fail("merchant UI does not default its runtime API URL to /api")
    forbidden = {
        "PINGBIZ_MERCHANT_IDENTIFIER", "PINGBIZ_STORE_IDENTIFIER",
        "PINGBIZ_MERCHANT_API_KEY", "ESTORE_CLIENT_SECRET",
        "KC_BOOTSTRAP_ADMIN_PASSWORD", "KC_DB_PASSWORD", "BIZ_APP_BASE_URL",
    }
    findings = []
    for path in ui_root.rglob("*"):
        if not path.is_file() or any(part in {"node_modules", ".git", ".angular"} for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in forbidden:
            if name in content:
                findings.append(f"{path.relative_to(ROOT)}:{name}")
    if findings:
        fail("server credential names found in frontend: " + ", ".join(findings[:10]))
    else:
        ok("frontend uses runtime /api configuration and contains no server credential names")


def validate_compose() -> None:
    path = ROOT / "deployment/compose/compose.yaml"
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    expected = {"postgres", "keycloak", "keycloak-realm-bootstrap", "estore-app", "merchant-store", "edge"}
    if set(services) != expected:
        fail(f"Compose service set mismatch: {sorted(services)}")
    exposed = [name for name, svc in services.items() if svc.get("ports")]
    if exposed != ["edge"]:
        fail(f"only edge may publish host ports; found {exposed}")
    raw = path.read_text(encoding="utf-8")
    required = [
        "ESTORE_PUBLIC_BASE_URL: https://${STORE_DOMAIN:?STORE_DOMAIN is required}/api",
        "ESTORE_KC_SERVER_URL: http://keycloak:8080",
        "ESTORE_APP_PUBLIC_URL: /api",
        "condition: service_completed_successfully",
        "KC_HOSTNAME: https://${STORE_DOMAIN:?STORE_DOMAIN is required}/auth",
    ]
    for fragment in required:
        if fragment not in raw:
            fail(f"Compose missing required contract: {fragment}")
    if "KC_HTTP_RELATIVE_PATH" in raw:
        fail("Compose must not combine edge /auth prefix stripping with KC_HTTP_RELATIVE_PATH")
    ok("Compose enforces the agreed deployment order and exposes only the edge")


def validate_qovery() -> None:
    versions = text("deployment/qovery/versions.tf")
    main = text("deployment/qovery/main.tf")
    variables = text("deployment/qovery/variables.tf")
    if 'source  = "qovery/qovery"' not in versions:
        fail("Qovery provider source address must be qovery/qovery")
    if 'version = "= 0.86.1"' not in versions:
        fail("Qovery provider is not pinned to reviewed version 0.86.1")
    if main.count("publicly_accessible = true") != 1:
        fail("Qovery adapter must expose exactly one public port")
    if 'variable "pingbusiness_environment"' not in variables:
        fail("Qovery adapter must carry pingbusiness_environment metadata")
    for fragment in [
        'name           = "01-database"', 'name           = "02-identity"',
        'name           = "03-realm-bootstrap"', 'name           = "04-backend"',
        'name           = "05-frontend"', 'name           = "06-edge"',
        'value = "${local.public_base_url}/api"',
        'value = "${local.public_base_url}/auth"',
        '{ key = "ESTORE_APP_PUBLIC_URL", value = "/api" }',
        'generate_certificate = true',
    ]:
        if fragment not in main:
            fail(f"Qovery adapter missing required contract: {fragment}")
    if 'variable "kit_repository_root_path"' not in variables or '${local.kit_root_path}/keycloak' not in main:
        fail("Qovery adapter is not monorepo-root aware")
    if re.search(r'variable\s+"(?:api|auth)_domain"', variables):
        fail("Qovery adapter contains obsolete multi-domain variables")
    ok("Qovery adapter is single-host, staged, private-by-default, and certificate-enabled")


def validate_northflank() -> None:
    template = json.loads(text("deployment/northflank/template.json"))
    arguments = template.get("arguments", {})
    if not isinstance(arguments, dict):
        fail("Northflank arguments must be an object")
        return
    expected_placeholders = {
        "KEYCLOAK_ADMIN_PASSWORD": "__GENERATE_SECURE_OVERRIDE__",
        "ESTORE_CLIENT_SECRET": "__GENERATE_SECURE_OVERRIDE__",
        "PINGBIZ_MERCHANT_IDENTIFIER": "__REQUIRED_SECRET_OVERRIDE__",
        "PINGBIZ_STORE_IDENTIFIER": "__REQUIRED_SECRET_OVERRIDE__",
        "PINGBIZ_MERCHANT_API_KEY": "__REQUIRED_SECRET_OVERRIDE__",
    }
    for key, expected in expected_placeholders.items():
        if arguments.get(key) != expected:
            fail(f"Northflank committed secret placeholder mismatch for {key}")
    if arguments.get("KIT_REPOSITORY_URL") != PUBLIC_REPOSITORY_URL or arguments.get("KIT_REPOSITORY_ROOT_PATH") != PUBLIC_KIT_ROOT_PATH:
        fail("Northflank template does not target the canonical monorepo kit path")
    if arguments.get("PINGBUSINESS_ENVIRONMENT") != "staging" or arguments.get("BIZ_APP_BASE_URL") != BIZ_APP_URLS["staging"]:
        fail("Northflank committed example must default to staging-derived biz-app URL")
    if template.get("argumentOverrides") != {}:
        fail("Northflank committed argumentOverrides must be empty")
    public_true = 0
    for key, value in walk_values(template):
        if key == "public" and value is True:
            public_true += 1
    if public_true != 1:
        fail(f"Northflank template must expose exactly one public port; found {public_true}")
    rendered = json.dumps(template)
    for path_fragment in [
        "${args.KIT_REPOSITORY_ROOT_PATH}/keycloak",
        "${args.KIT_REPOSITORY_ROOT_PATH}/source/estore-app",
        "${args.KIT_REPOSITORY_ROOT_PATH}/deployment/edge",
    ]:
        if path_fragment not in rendered:
            fail(f"Northflank adapter missing monorepo build path: {path_fragment}")
    for fragment in [
        '"ESTORE_APP_PUBLIC_URL": "/api"',
        '"ESTORE_PUBLIC_BASE_URL": "https://${args.STORE_DOMAIN}/api"',
        '"KC_HOSTNAME": "https://${args.STORE_DOMAIN}/auth"',
        '"GUNICORN_WORKERS": "2"',
        '"GUNICORN_THREADS": "4"',
        '"autorun": false',
    ]:
        if fragment not in rendered:
            fail(f"Northflank adapter missing required contract: {fragment}")
    ok("Northflank template is sequential, secret-override driven, and exposes one edge")


def validate_railway() -> None:
    service_map = json.loads(text("deployment/railway/service-map.json"))
    services = service_map.get("services", [])
    names = {service.get("name") for service in services}
    expected = {"postgres", "keycloak", "keycloak-realm-bootstrap", "estore-app", "merchant-store", "edge"}
    if names != expected:
        fail(f"Railway service map mismatch: {sorted(names)}")
    public = [service.get("name") for service in services if service.get("public") is True]
    if public != ["edge"]:
        fail(f"Railway must expose exactly one edge service; found {public}")
    rendered = json.dumps(service_map)
    if service_map.get("repository", {}).get("url") != PUBLIC_REPOSITORY_URL:
        fail("Railway service map does not target the canonical repository")
    for service in services:
        if service.get("sourceRoot") and not service["sourceRoot"].startswith(PUBLIC_KIT_ROOT_PATH + "/"):
            fail(f"Railway service sourceRoot is not monorepo-aware: {service.get('name')}")
    bootstrap = next((service for service in services if service.get("name") == "keycloak-realm-bootstrap"), {})
    if bootstrap.get("sourceRoot") != PUBLIC_KIT_ROOT_PATH + "/keycloak" or bootstrap.get("dockerfilePath") != "realm-bootstrap/Dockerfile":
        fail("Railway realm-bootstrap build must use keycloak as context so the realm template is available")
    for fragment in ["/", "/api/*", "/auth/*", "keycloak.railway.internal:8080", "estore-app.railway.internal:5000"]:
        if fragment not in rendered and fragment not in text("deployment/railway/README.md"):
            fail(f"Railway adapter missing route/internal DNS hint: {fragment}")
    if "PINGBIZ_MERCHANT_API_KEY" not in text("deployment/railway/README.md") and "PINGBIZ_MERCHANT_API_KEY" not in text("deployment/railway/variables.example.json"):
        fail("Railway adapter must document merchant API key secret handling")
    ok("Railway adapter defines private services, one public edge, and service variables")


def validate_coolify() -> None:
    compose = yaml.safe_load(text("deployment/coolify/compose.yaml"))
    services = compose.get("services", {})
    expected = {"postgres", "keycloak", "keycloak-realm-bootstrap", "estore-app", "merchant-store", "edge"}
    if set(services) != expected:
        fail(f"Coolify service set mismatch: {sorted(services)}")
    exposed_ports = [name for name, svc in services.items() if svc.get("ports")]
    if exposed_ports:
        fail("Coolify adapter must not map host ports directly: " + ", ".join(exposed_ports))
    edge = services.get("edge", {})
    env = edge.get("environment", {})
    if "SERVICE_FQDN_EDGE_8080" not in env:
        fail("Coolify edge must use SERVICE_FQDN_EDGE_8080 for proxy domain binding")
    for private_name in ["postgres", "keycloak", "estore-app", "merchant-store"]:
        if services.get(private_name, {}).get("ports") or "SERVICE_FQDN" in json.dumps(services.get(private_name, {})):
            fail(f"Coolify private service is exposed: {private_name}")
    if PUBLIC_KIT_ROOT_PATH + "/deployment/coolify/compose.yaml" not in text("deployment/coolify/README.md"):
        fail("Coolify documentation does not identify the monorepo Compose path")
    if "https://biz-app.staging.pingbusiness.org" not in text("deployment/coolify/env.example"):
        fail("Coolify env example must default to staging-derived biz-app URL")
    ok("Coolify adapter uses Compose, private services, one proxy-bound edge, and required variables")


def validate_website() -> None:
    html = text("website/pingbusiness-store-launcher.html")
    for fragment in ["Customize UI", "Deploy store", "Railway", "Coolify", "Qovery", "Northflank", BIZ_APP_URLS["staging"], BIZ_APP_URLS["production"]]:
        if fragment not in html:
            fail(f"website prompt generator missing {fragment!r}")
    if re.search(r'<input[^>]+id=["\'].*api.*key', html, re.IGNORECASE):
        fail("static prompt generator must not contain an API-key input field")
    if "Do not paste the merchant API key" not in html:
        fail("static prompt generator must warn against API-key prompt exposure")
    for fragment in [PUBLIC_REPOSITORY_URL, PUBLIC_KIT_ROOT_PATH, PUBLIC_KIT_TREE_URL, PUBLIC_AGENT_ENTRYPOINT_URL]:
        if fragment not in html:
            fail(f"static prompt generator is missing canonical source metadata: {fragment}")
    if re.search(r'<input[^>]+(?:kit|repo)(?:url|repository)', html, re.IGNORECASE):
        fail("static prompt generator must not allow the authoritative kit repository URL to be edited")
    if "Git clone URL" not in html or "do not attempt to clone the GitHub tree URL" not in html:
        fail("deployment prompt must distinguish the clone URL from the GitHub tree URL")
    if "Preserve LICENSE, NOTICE, TRADEMARKS.md, and THIRD_PARTY_NOTICES.md" not in html:
        fail("design prompt must preserve Apache-2.0 licensing companion files")
    if "navigator.clipboard.writeText" not in html:
        fail("static prompt generator must support copying prompts")
    ok("fixed-source static HTML generator supports design/deploy prompts without API-key capture")


def validate_documents() -> None:
    stale = re.compile(
        r"apiDomain|authDomain|api\.store|auth\.store|three[- ]domain|three[- ]host|"
        r"ESTORE_PUBLIC_BASE_URL=https://api|KC_HTTP_RELATIVE_PATH|REPLACE_WITH_PING_BUSINESS_BIZ_APP_URL",
        re.IGNORECASE,
    )
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {"node_modules", ".git", "__pycache__", ".generated"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".md", ".json", ".yaml", ".yml", ".tf", ".example", ".sh", ".html"} and not path.name.endswith(".env.example"):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if stale.search(content):
            hits.append(str(path.relative_to(ROOT)))
    if hits:
        fail("stale multi-domain/path or free-form biz-app placeholder remains in: " + ", ".join(hits))
    else:
        ok("documentation and examples consistently use one public hostname and derived biz-app URLs")
    license_text = text("LICENSE")
    if "Apache License" not in license_text or "Version 2.0, January 2004" not in license_text:
        fail("LICENSE is not the Apache License 2.0 text")
    for required in ["NOTICE", "TRADEMARKS.md", "THIRD_PARTY_NOTICES.md"]:
        if not (ROOT / required).is_file():
            fail(f"missing licensing companion file: {required}")
    package = json.loads(text("source/merchant-store/package.json"))
    if package.get("license") != "Apache-2.0":
        fail("merchant-store package metadata must declare Apache-2.0")
    for component in ["source/merchant-store", "source/estore-app"]:
        if text(f"{component}/LICENSE") != license_text:
            fail(f"{component} must contain the exact Apache-2.0 LICENSE for standalone redistribution")
        if text(f"{component}/NOTICE") != text("NOTICE"):
            fail(f"{component} must contain the kit NOTICE for standalone redistribution")
    metadata = json.loads(text("kit-metadata.json"))
    repository = metadata.get("repository", {})
    release = metadata.get("release", {})
    if metadata.get("version") != text("VERSION").strip() or metadata.get("license") != "Apache-2.0":
        fail("kit-metadata.json version/license mismatch")
    if repository != {
        "url": PUBLIC_REPOSITORY_URL,
        "branch": "main",
        "rootPath": PUBLIC_KIT_ROOT_PATH,
        "treeUrl": PUBLIC_KIT_TREE_URL,
        "agentEntrypointUrl": PUBLIC_AGENT_ENTRYPOINT_URL,
    }:
        fail("kit-metadata.json canonical repository metadata mismatch")
    if release.get("latestStableAssetUrl") != PUBLIC_RELEASE_ASSET_URL:
        fail("kit-metadata.json stable release URL mismatch")
    if (ROOT / "LICENSE-DECISION-REQUIRED.md").exists():
        fail("obsolete license-decision blocker is still present")
    ok("Apache-2.0 licensing, component copies, metadata, notices, and trademark boundary are present")
    placeholder_hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {"node_modules", ".git", "__pycache__", ".generated"} for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        placeholder_tokens = (
            "REPLACE" + "_WITH_PUBLISHED_KIT_REPOSITORY",
            "REPLACE" + "-WITH-VIBE-KIT-REPOSITORY",
        )
        if any(token in content for token in placeholder_tokens):
            placeholder_hits.append(str(path.relative_to(ROOT)))
    if placeholder_hits:
        fail("public GitHub repository placeholders remain: " + ", ".join(sorted(set(placeholder_hits))))
    if PUBLIC_REPOSITORY_URL not in text("PUBLISHING.md") or PUBLIC_KIT_TREE_URL not in text("PUBLISHING.md"):
        fail("PUBLISHING.md is missing canonical public URLs")
    workflow = text("github/merchant-store-vibe-kit-validate.yml")
    if "merchant-store-vibe-coding-kit/**" not in workflow or "working-directory: ${{ env.KIT_DIR }}" not in workflow:
        fail("GitHub Actions workflow is not monorepo-aware")
    ok("public URLs contain no publication placeholders and monorepo CI is supplied")


def main() -> int:
    validate_required_files()
    validate_hashes()
    validate_input_schema()
    validate_realm()
    validate_ui()
    validate_compose()
    validate_qovery()
    validate_northflank()
    validate_railway()
    validate_coolify()
    validate_website()
    validate_documents()

    for message in passes:
        print(f"PASS: {message}")
    for message in warnings:
        print(f"WARN: {message}")
    for message in errors:
        print(f"FAIL: {message}", file=sys.stderr)
    print(f"Summary: {len(passes)} passed, {len(warnings)} warnings, {len(errors)} failed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
