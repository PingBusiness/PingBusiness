# Platform support

The vibe kit supports five deployment targets:

| Target | Role | Status in this kit |
| --- | --- | --- |
| Compose | Local/reference deterministic stack | Fully specified reference deployment |
| Qovery | Agentic infrastructure / BYOC-friendly PaaS | Terraform adapter |
| Northflank | Template-driven managed platform | Dynamic template adapter |
| Railway | Managed PaaS and Railway MCP/agent workflow | Service-map adapter for template/MCP creation |
| Coolify | Merchant-owned VPS/self-hosted PaaS | Docker Compose stack adapter |

All targets use the same public architecture:

```text
https://<store-domain>/       -> merchant-store UI
https://<store-domain>/api/*  -> estore-app
https://<store-domain>/auth/* -> Keycloak
```

The merchant selects `staging` or `production`; the deployment generator derives the correct Ping Business `BIZ_APP_BASE_URL`:

```text
staging    -> https://biz-app.staging.pingbusiness.org
production -> https://biz-app.pingbusiness.org
```

The public merchant flow must not expose a free-form `BIZ_APP_BASE_URL` input and must not include the merchant API key in an AI prompt. The API key is entered only when the agent creates the platform secret.
