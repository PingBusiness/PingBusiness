# Railway deployment adapter

This adapter lets a Railway-capable agent or Railway MCP workflow deploy the PingBusiness merchant-store stack from the public vibe-kit repository.

Railway supports reusable templates that capture multiple services and required variables, services from GitHub repositories or Docker images, private networking between services, custom domains, and automatic TLS. The adapter is therefore structured as an agent-readable service plan rather than a single Compose file.

Railway source roots in `service-map.json` are relative to the monorepo and begin with `/merchant-store-vibe-coding-kit/`.

## Service topology

Create these services in one Railway project/environment:

1. `postgres` - Railway PostgreSQL template/service.
2. `keycloak` - Docker service from `keycloak/Dockerfile`.
3. `keycloak-realm-bootstrap` - one-shot Docker service built with root `keycloak/` and Dockerfile `keycloak/realm-bootstrap/Dockerfile`; run after Keycloak is healthy.
4. `estore-app` - Docker service from `source/estore-app/Dockerfile`.
5. `merchant-store` - Docker service from `source/merchant-store/Dockerfile` or a customized UI repository.
6. `edge` - Docker service from `deployment/edge/Dockerfile`; the only public service.

The `edge` service receives the custom domain and routes:

- `/` -> `merchant-store`
- `/api/*` -> `estore-app`
- `/auth/*` -> `keycloak`

## Generated inputs

Run:

```sh
python3 scripts/prepare-deployment.py   --input deployment-input.json   --repository-url https://github.com/PingBusiness/PingBusiness   --repository-root-path /merchant-store-vibe-coding-kit   --output-dir .generated
```

For `platform: "railway"`, the helper writes:

- `.generated/railway/deployment-plan.json` - non-secret service and domain plan.
- `.generated/railway/service-variables.secret.json` - variables that must be imported into each Railway service.

Do not commit `.generated/`.

## PingBusiness environment

The merchant selects only `staging` or `production`. The deployment helper derives `BIZ_APP_BASE_URL`:

- `staging` -> `https://biz-app.staging.pingbusiness.org`
- `production` -> `https://biz-app.pingbusiness.org`

The generated prompt must not ask the merchant to type a free-form biz-app URL.

## Template publication note

A public Railway template is created from a working Railway project. Use `deployment/railway/service-map.json` as the authoritative blueprint when building that project or when operating through Railway MCP/CLI.
