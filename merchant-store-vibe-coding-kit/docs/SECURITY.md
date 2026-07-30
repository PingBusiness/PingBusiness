# Security requirements

## Secrets

Server-only secrets include Ping Business merchant/store credentials, ESTORE
client secret, Keycloak administrator password, PostgreSQL/SMTP credentials,
and hosting/DNS tokens. Store them in encrypted platform controls, inject them
only into required workloads, redact logs, and exclude them from Git, images,
build layers, browser assets, source maps, and public reports.

## Browser rules

- Browser calls only same-origin `/api`.
- It never creates Ping Business server headers or calls central `biz-app`.
- It never calls Keycloak administration, PostgreSQL, or PaymentAsia APIs directly.
- Tokens are not logged or sent to analytics.
- `postMessage` is a wake-up hint, never payment proof.
- Merchant HTML/SVG is not injected unsafely.

## Same-origin and proxy trust

Production values:

```text
ESTORE_ALLOWED_ORIGINS=https://<store-domain>
ESTORE_TRUST_PROXY_HEADERS=true
ESTORE_CHECKOUT_FRAME_ANCESTORS='self'
```

Proxy trust is safe only because the backend is private and the edge overwrites
`Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and `X-Forwarded-Port`.

## Keycloak

- PostgreSQL only; no development database.
- Public URL is `https://<store-domain>/auth` through the edge.
- Private HTTP and management ports remain unexposed.
- Bootstrap credentials are generated and protected.
- Realm bootstrap is idempotent.
- Service account receives `view-realm` and `manage-users`, not realm-admin.
- Brute-force protection is intentionally disabled in this release unless the merchant explicitly changes policy.

## Network exposure

Only the edge public port is permitted. Verify externally that PostgreSQL,
Keycloak `9000`, raw Keycloak `8080`, backend `5000`, and UI `80` are not
reachable.

## Supply chain

Pin repository commits, provider versions, base-image versions/digests for a
production release, review dependency changes, scan images and frontend bundles,
and retain build/test evidence.
