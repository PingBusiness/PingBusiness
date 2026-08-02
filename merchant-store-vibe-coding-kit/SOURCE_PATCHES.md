# Pipeline-enablement changes

Product behavior was preserved while deployment-specific files were added or
changed.

## Merchant UI

Relative to `merchant-store-master(1).zip`:

- `src/app/app.configs.ts` reads `window.__PINGBUSINESS_CONFIG__.apiUrl` and keeps `http://localhost:5000` only as a local-development fallback.
- `src/index.html` loads `/assets/runtime-config.js` before Angular bootstraps.
- `src/assets/runtime-config.js` supplies the local-development default.
- `src/assets/healthz` provides a static container health endpoint.
- `docker-entrypoint.sh` validates `ESTORE_APP_PUBLIC_URL` and writes runtime config at startup; production defaults to `/api`.
- `docker/apache-angular.conf` adds SPA fallback, no-cache runtime config, health routing, and baseline security headers.
- `Dockerfile` performs a production Angular build and serves it with Apache.
- `.dockerignore` excludes local, generated, and secret material.

No server credential is written to the frontend.

## `estore-app`

- `app.py` and `requirements.txt` are byte-identical to the canonical files in `pingbiz-master(26).zip`.
- The canonical Dockerfile/build scripts are included with the backend source.
- Deployment templates use the canonical `GUNICORN_WORKERS`, `GUNICORN_THREADS`, and `GUNICORN_TIMEOUT` variables.

## Keycloak

- The supplied legacy Keycloak Dockerfile was used only as reference.
- `keycloak/Dockerfile` uses modern Keycloak `26.7.0`, PostgreSQL optimization, health/management port `9000`, and startup realm import.
- `ESTORE-realm-template.json` is portable, contains no live secret, and keeps brute-force protection disabled.
- `ESTORE-realm-template.json` gives the `${ESTORE_CLIENT_ID}` client an
  `estore-app-audience` protocol mapper (`oidc-audience-mapper`). `estore-app`
  validates customer tokens through Keycloak's introspection endpoint, and
  Keycloak 26.7 rejects that call unless the introspecting client appears in the
  token `aud`. Customers hold no client roles on `estore-app`, so the default
  `audience resolve` mapper supplies none. Without this mapper login succeeds but
  every authenticated endpoint returns 401 with `INTROSPECT_TOKEN_ERROR ...
  "Client 'estore-app' is not in the token audience"`.
- `realm-bootstrap/` adds idempotent reconcile-and-verify behavior because startup import intentionally does not overwrite an existing realm.

## Public edge

- Caddy exposes one hostname.
- `/api/image/<file_id>` is matched ahead of the general `/api/*` handler and has
  its `Cache-Control` replaced with `public, max-age=31536000, immutable`.
  Product images are immutable by `file_id`, but biz-app sends
  `Cache-Control: no-cache` and `estore-app` relays it verbatim, so without this
  override every image is revalidated on every page view. Browser and platform-CDN
  caching are enabled by the header alone; Caddy has no stock equivalent of
  nginx `proxy_cache`, and `deployment/edge/README.md` records the optional
  `cache-handler` build for deployments that need a shared origin cache.
- `/api` is stripped and forwarded privately to `estore-app`.
- `/auth` is stripped and forwarded privately to Keycloak, whose fixed public hostname remains `https://<store-domain>/auth`.
- all other paths are forwarded privately to the UI.

## v1.0.0-rc3 deployment expansion

- Added Railway support under `deployment/railway/` with an agent-readable service map, variable example, and documentation for Railway template/MCP workflows.
- Added Coolify support under `deployment/coolify/` with a Docker Compose stack that exposes only the edge service through Coolify's proxy and keeps PostgreSQL, Keycloak, `estore-app`, and the UI private.
- Added `pingbusinessEnvironment` to the deployment input schema. Merchants choose only `staging` or `production`; `scripts/prepare-deployment.py` derives `BIZ_APP_BASE_URL` as either `https://biz-app.staging.pingbusiness.org` or `https://biz-app.pingbusiness.org`.
- Added `website/pingbusiness-store-launcher.html`, a static prompt generator for the design and deployment workflows. It does not collect the merchant API key and instructs the deployment agent to request it only while creating the platform secret.
- Updated agent and deployment prompts to cover Qovery, Northflank, Railway, and Coolify.

## v1.0.0-rc3 publication and licensing

- Applied Apache License 2.0 to the kit and added NOTICE, trademark guidance, contributor guidance, and direct third-party notices.
- Fixed the canonical public location as `https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit`.
- Made Qovery, Northflank, Railway, Coolify, the deployment generator, and examples monorepo-aware through `/merchant-store-vibe-coding-kit`.
- Renamed the static launcher to `website/pingbusiness-store-launcher.html` and embedded the canonical kit URL.
- Added a repository-root GitHub Actions workflow payload for validation after upload to `PingBusiness/PingBusiness`.

- Made the launcher repository URL fixed rather than merchant-editable and added exact clone/branch/root metadata to generated prompts.
- Added `kit-metadata.json` and component-local license/notice copies for standalone UI/backend redistribution.
