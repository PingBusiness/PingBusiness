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

## Platform reduction

- Removed the Qovery adapter (`deployment/qovery/`) and the Coolify adapter
  (`deployment/coolify/`). The supported platform set is now Compose, Railway,
  and Northflank in `deployment/deployment-input.schema.json`,
  `scripts/prepare-deployment.py`, `kit-metadata.json`, the launcher page, and
  the agent instructions.
- Dropped `uiSource.qoveryGitTokenId` and `database.instanceType` from the
  deployment input schema; both existed only for the Qovery adapter. The rest of
  the `database` block is still validated for the deployment agent even though
  the remaining adapters size PostgreSQL through their own plan arguments.

## Self-hosting and tool-less agents

- Added `deployment/SELF_HOSTING.md`, the merchant-facing runbook for running the
  store on a merchant-owned server: sizing, Docker, the single DNS A record, the
  requirement that inbound 80/443 stay open, automatic Let's Encrypt issuance and
  renewal through Caddy, the DNS-only-CDN caveat, and the backup duty the
  merchant takes on. This replaces the merchant-owned-VPS role that the removed
  Coolify adapter used to fill; it needs no new adapter, because self-hosting is
  the existing Compose adapter with a real hostname and without `--local`.
- Added a self-hosted target to `website/pingbusiness-store-launcher.html`. It is
  a launcher-level choice that maps to `platform: "compose"`, keeps the hostname
  and DNS fields active, and disables the region selector, which does not apply
  to a machine the merchant already owns. The generated prompt makes the agent
  confirm every prerequisite before generating anything.
- Made every deployment prompt require the agent to declare, before collecting
  merchant values, whether it can clone a repository, run `python3`, run shell
  commands, and call the platform API — and to switch to step-by-step guidance
  with real command output when it cannot. Chat-only assistants previously had no
  instruction to say so, and no agent can reach a merchant's private server.
  `scripts/prepare-deployment.py` is standard-library-only precisely so that a
  merchant can run it themselves rather than have secrets invented in a chat
  transcript.
- Documented the merchant API key handoff for a self-hosted deployment: the key
  is entered on the server with `read -rs`, so it stays out of shell history and
  off every command line, and an assisting agent is told this is the one step it
  must not perform even when it has shell access.

## The kit UI is a reference implementation, not a storefront

`source/merchant-store/` is where a customization starts and an example of the
contracts a storefront must satisfy. It carries demonstration branding and is
never deployed. That is now enforced rather than merely stated:

- `uiSource.mode` is `git` or `local`; the `bundled` mode that built the kit's
  own tree is gone. `local` takes an absolute `uiSource.path` to a customized
  tree on the machine running Compose, which also gives the attached-ZIP flow a
  real mode instead of a hand-edited `MERCHANT_STORE_BUILD_CONTEXT`.
- `local` is rejected for managed platforms, which build from Git and cannot see
  a merchant's disk.
- `scripts/prepare-deployment.py` rejects a `uiSource` that resolves to the kit's
  own `source/merchant-store`, by path for `local` and by repository plus root
  path for `git`.
- The committed Northflank template no longer defaults `UI_REPOSITORY_URL`,
  `UI_DOCKER_WORK_DIR`, or `UI_DOCKERFILE_PATH` to the kit's UI, and the Railway
  service map no longer gives `merchant-store` a kit source root.
- The launcher dropped the "Use the default UI from the kit" option, and every
  deployment prompt tells the agent to stop and ask for a customized UI rather
  than fall back to the kit's storefront.

## Assistants that cannot retrieve the kit

`AGENTS.md` previously said "Do not ask a merchant to download and re-upload
files that are already public." That is right for an agent with repository or web
access and actively wrong for a chat-only assistant, which was left with no
sanctioned way to obtain the kit and would fill the gap from memory.

- `AGENTS.md` now prefers self-retrieval, and states the fallback explicitly: say
  so first, ask the merchant to attach the release archive, name the files needed
  if the archive is impractical, and never reconstruct the kit from memory.
- All five generated prompts — design, local preview, self-hosted, and both
  managed platforms — carry the same fallback and the downloadable archive URL,
  so a merchant using Gemini or another browser-only assistant is told what to do
  rather than being handed an invented architecture.
- The capability declaration now leads with kit retrieval rather than assuming an
  agent that has already read the files.
- `design/DESIGN_AGENT.md` carries the same rule at the step that reads the UI
  source, because a customization built on a remembered Angular app satisfies no
  runtime-config, trust-boundary, or checkout contract that the deployment later
  depends on.
