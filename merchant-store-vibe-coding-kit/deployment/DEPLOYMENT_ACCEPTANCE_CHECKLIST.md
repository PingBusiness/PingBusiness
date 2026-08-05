# Deployment acceptance checklist

Record evidence for every item.

## Source and input

- [ ] Public kit and selected UI are pinned to commit SHAs.
- [ ] Input validates against `deployment-input.schema.json`.
- [ ] One merchant-controlled store hostname is recorded.
- [ ] No secret appears in Git, browser assets, logs, plan output, or public report.

## PostgreSQL

- [ ] PostgreSQL is private and persistent.
- [ ] Keycloak has isolated credentials/database context.
- [ ] Automated backups, retention, alerts, and restore instructions are recorded.

## Keycloak

- [ ] Keycloak uses PostgreSQL and private ports `8080`/`9000`.
- [ ] Public hostname is `https://<store-domain>/auth` through the edge.
- [ ] ESTORE realm is enabled.
- [ ] Confidential `estore-app` client has generated secret, direct grants, and service account.
- [ ] Service account has `view-realm` and `manage-users`, not realm-admin.
- [ ] Reconcile/verification job passes.
- [ ] Brute-force protection remains disabled unless explicitly approved.

## `estore-app`

- [ ] Required values are stored in protected platform controls.
- [ ] Internal Keycloak URL is used.
- [ ] `ESTORE_PUBLIC_BASE_URL=https://<store-domain>` — the store root, with no
      `/api` suffix, so PaymentAsia callbacks match the exact paths biz-app pins.
- [ ] `ESTORE_ALLOWED_ORIGINS=https://<store-domain>`.
- [ ] Proxy trust is enabled only behind the controlled edge.
- [ ] Startup merchant/store scope resolution succeeds.
- [ ] Private `/health` passes and public `/api/health` passes.

## Merchant UI

- [ ] Source/image is pinned.
- [ ] `ESTORE_APP_PUBLIC_URL=/api` is injected at startup.
- [ ] Runtime config contains only `/api` or the approved public API URL.
- [ ] `/healthz` and SPA route refresh pass.
- [ ] Browser bundles contain no secret or direct central `biz-app` URL.

## Edge, DNS, and TLS

- [ ] Edge is the only public service.
- [ ] `/` -> UI, `/api` -> backend, `/auth` -> Keycloak.
- [ ] One DNS record points to the correct platform target.
- [ ] Certificate is valid and renewal is managed.
- [ ] Forwarded host/proto/port are overwritten by the trusted edge.
- [ ] PostgreSQL and Keycloak management port are unreachable publicly.

## Functional tests

- [ ] Store/catalogue/product/media/inventory reads work.
- [ ] Registration, login, refresh, profile, password change, and logout work.
- [ ] Ordinary checkout initiation/status works in staging.
- [ ] Subscription initiation/status works when applicable.
- [ ] Customer order/order-item/payment reads work.
- [ ] Browser makes no direct call to central `biz-app`, Keycloak admin, PostgreSQL, or PaymentAsia APIs.

## Handoff

- [ ] Monitoring and secret-redacted logs are configured.
- [ ] Merchant receives store, API, Keycloak admin, and hosting-console URLs.
- [ ] Merchant receives protected secret locations and rotation steps, not public raw values.
- [ ] Report records platform/provider versions, IDs, DNS, checks, backup status, and limitations.
