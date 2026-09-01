# Platform support

The vibe kit supports three deployment targets:

| Target | Role | Status in this kit |
| --- | --- | --- |
| Compose | Local preview, and self-hosting on a merchant-owned server or VPS | Fully specified reference deployment |
| Northflank | Template-driven managed platform | Dynamic template adapter |
| Railway | Managed PaaS and Railway MCP/agent workflow | Service-map adapter for template/MCP creation |

The Compose adapter covers two merchant-facing choices. With `--local` and
`storeDomain: localhost` it is a preview on the merchant's own machine, served
over plain HTTP with no certificate. With a real hostname and no `--local` it is
a self-hosted production deployment: the edge publishes ports 80/443 and Caddy
obtains and renews a Let's Encrypt certificate automatically. The merchant
supplies the server, the DNS record, and the open ports, and takes on backups and
patching. See `deployment/SELF_HOSTING.md`.

All targets use the same public architecture:

```text
https://<store-domain>/       -> merchant-store UI
https://<store-domain>/api/*  -> estore-app
https://<store-domain>/auth/* -> Keycloak
```

The merchant selects `staging` or `production`; the deployment generator derives the correct PingBusiness `BIZ_APP_BASE_URL`:

```text
staging    -> https://biz-app.staging.pingbusiness.org
production -> https://biz-app.pingbusiness.org
```

The public merchant flow must not expose a free-form `BIZ_APP_BASE_URL` input and must not include the merchant API key in an AI prompt. The API key is entered only when the agent creates the platform secret.
