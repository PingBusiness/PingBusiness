# Ping Business merchant-store architecture

## Purpose

Each merchant hosts an independently branded storefront and customer identity
environment. Central Ping Business remains authoritative for merchant, store,
product, inventory, order, and payment records.

## One-domain public surface

```text
https://shop.example.com/       merchant UI
https://shop.example.com/api/*  estore-app
https://shop.example.com/auth/* Keycloak
```

A public edge service terminates/runs behind TLS and strips the route prefixes
before forwarding to private services.

## Components

### Merchant UI

Public Angular browser code. It handles presentation, customer session state,
cart state, catalogue/media reads, checkout launch, recurring enrollment, and
customer-scoped order/payment reads. Its only deployment value is:

```text
ESTORE_APP_PUBLIC_URL=/api
```

### `estore-app`

The Flask service is the browser-facing API and security boundary. It manages
customer identity through Keycloak, scopes all central Ping Business access with
server-side merchant credentials, exposes approved catalogue/inventory/media,
creates checkout intents, processes callbacks, and exposes customer-scoped
orders/payments.

### Keycloak and PostgreSQL

The merchant owns the ESTORE realm and customer identities. Keycloak uses
private PostgreSQL persistence. The `estore-app` service account has only
`view-realm` and `manage-users` among realm-management roles.

### Edge

Only the edge has a public port/domain. It overwrites forwarding headers, routes
same-origin requests, and prevents direct exposure of UI, API, identity, and
database service ports.

## Trust boundary

```text
Untrusted browser -> public edge -> private estore-app
                                      |-> private Keycloak -> PostgreSQL
                                      +-> central biz-app over HTTPS
```

The browser never receives merchant API credentials, client/admin secrets, or
database credentials.

## Authentication lifecycle

1. UI posts credentials to `/api/login`.
2. Edge forwards to private `estore-app /login`.
3. Backend exchanges with private Keycloak using the confidential client.
4. UI keeps customer session data in session storage.
5. Refresh and logout go through `/api/refresh` and `/api/logout`.

## Checkout callbacks

`ESTORE_PUBLIC_BASE_URL=https://<store-domain>/api` causes return and notification
URLs to point to the public edge, which strips `/api` before forwarding to the
backend. Payment completion is accepted only from authoritative backend status,
not browser messages.

## Dependency graph

```text
validated input/secrets
  -> private PostgreSQL
  -> private Keycloak
  -> realm reconcile/verify
  -> private estore-app
  -> private UI
  -> public edge
  -> one DNS record/TLS
  -> functional and exposure verification
```
