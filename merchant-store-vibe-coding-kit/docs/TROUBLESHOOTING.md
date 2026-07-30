# Troubleshooting

## Keycloak cannot connect to PostgreSQL

Check private host/port, database readiness, database username/password, TLS mode, and whether the managed database permits the Keycloak workload. Do not make PostgreSQL public as a shortcut.

## Realm verification fails

- Confirm the realm name, client ID, and client secret match.
- Confirm startup import ran on a new database.
- Remember that startup import skips an existing realm.
- Inspect the service-account role mappings for `view-realm` and `manage-users`.
- Verify the job uses the private Keycloak URL ending in `/auth`.

## `estore-app` exits during startup

The canonical app resolves merchant/store scope through `biz-app` at startup. Check:

- `BIZ_APP_BASE_URL` and outbound HTTPS/DNS;
- merchant identifier;
- store identifier;
- merchant API key;
- whether the merchant/store is active and the key is current.

Do not suppress this failure; it prevents an incorrectly scoped store from starting.

## Browser CORS failure

Ensure `ESTORE_ALLOWED_ORIGINS` exactly matches the storefront origin including `https://` and port where relevant. Do not use `*` with authenticated production traffic.

## Wrong callback hostname or scheme

Check `ESTORE_PUBLIC_BASE_URL`, trusted proxy settings, and ingress forwarding headers. The public URL must be the storefront HTTPS origin followed by `/api`, not a Docker/private hostname.

## UI points to the wrong API

Fetch `/assets/runtime-config.js` from the deployed UI. It should normally contain the root-relative value `/api`; a full HTTPS API URL is supported only for an intentionally split-domain deployment. Restart the UI with the correct `ESTORE_APP_PUBLIC_URL`; do not rebuild Angular solely for this change.

## SPA route returns 404

Confirm the supplied Apache config or platform equivalent routes unknown non-file paths to `index.html` while preserving real assets and `/healthz`.

## Checkout popup blocked

The UI must open the popup synchronously from the customer action, before asynchronous validation completes, and then submit the provider form after validation. Ask the customer to permit popups only when the browser still blocks it.

## Checkout appears complete but status remains pending

The UI correctly distrusts the browser return. Inspect provider notify/return logs and Ping Business verification, then continue authoritative status polling. Do not mark payment successful from a URL or message alone.

## Certificate remains pending

Verify the platform's validation record/target, authoritative DNS, proxy/CDN mode, CAA restrictions, and that the hostname is not linked elsewhere. Wait for real DNS resolution rather than bypassing certificate validation.

## Build fails while installing npm dependencies

Distinguish source errors from registry/network failures. Use a networked CI runner with the public or approved npm registry, retain `package-lock.json`, and report the exact failed package/request. Do not claim a build passed when dependencies were not installed.
