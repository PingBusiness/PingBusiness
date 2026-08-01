# Design-agent workflow

Customize `source/merchant-store/` only. Do not alter `source/estore-app/`,
Keycloak, database, central payment logic, or server-to-server behavior.

## Inputs

Collect missing high-value design information: merchant/store name, logo,
favicon, imagery, colour tokens, typography, tone/copy, navigation/layout,
accessibility/browser requirements, legal links, and inspiration references.
Do not request infrastructure credentials during design.

## Process

1. Read `AGENTS.md`, the API spec, UI reference architecture, and complete UI source.
2. Inventory assets using `ASSET_MANIFEST.md`.
3. State a concise design direction and map assets to destinations.
4. Customize the existing Angular application unless another client technology is explicitly required.
5. Preserve the runtime `/api` configuration and trust boundary.
6. Preserve routes and functional flows unless an approved change remains API-compatible.
7. Run clean dependency installation, production build, type/tests, responsive/accessibility checks, and secret scan.
8. Fix failures and rerun validation.
9. Preview the store locally and iterate with the merchant before handing off — see
   "Local preview" below and in `prompts/DESIGN_PROMPT.md`.
10. Return the complete customized `source/merchant-store` tree only. Do not vendor
    `deployment/`, `keycloak/`, `scripts/`, `prompts/`, `docs/`, `design/`,
    `website/`, or `source/estore-app` into the package — the merchant clones the
    kit for those, and a bundled copy is ignored at deploy time because every
    platform adapter clones the kit from its published repository.
11. Include `DESIGN_REPORT.md` with changed files, tokens, assets, commands/results, limitations, and deployment handoff.

## Deployment handoff

The customized UI must support:

```bash
docker build -t merchant-store-custom .
docker run --rm -e ESTORE_APP_PUBLIC_URL=/api -p 8080:80 merchant-store-custom
```

It must listen on port 80, answer `/healthz`, retain runtime config, and require
no compile-time store hostname. A customized repository must be suitable for an
agent to pass directly to Qovery or Northflank.

It must also keep an image-level `HEALTHCHECK`. Compose and Coolify gate the edge
on `condition: service_healthy` for `merchant-store`, and that condition is
satisfied only by the image's own healthcheck. A customized Dockerfile that drops
it passes every design check and then fails at `compose up` with
"has no healthcheck configured".

## Local preview

The merchant must be able to see the store running before committing to a
deployment. A static build cannot exercise the live catalogue, Keycloak, or
checkout, and nobody can approve a store they have never seen.

The preview needs a running `estore-app`, which needs the merchant identifier,
store identifier, and merchant API key. Those are not part of the design brief and
must not be requested in the design conversation. The design step therefore ships
the package plus `HANDOFF.md`, and the merchant runs the preview from the
launcher's **Deploy store** tab with hosting platform **Local preview (Docker
Compose on my machine)** and UI source **attached ZIP**.

`HANDOFF.md` must reproduce the commands so the merchant can also run them directly.
The package ships the UI only, so it starts by obtaining the kit:

```bash
git clone https://github.com/PingBusiness/PingBusiness.git
cd PingBusiness/merchant-store-vibe-coding-kit
python3 scripts/prepare-deployment.py --input deployment-input.json --local --output-dir .generated
cd deployment/compose
MERCHANT_STORE_BUILD_CONTEXT=/path/to/unzipped/merchant-store \
  docker compose --env-file ../../.generated/compose.env -f compose.yaml up --build -d
python3 ../../scripts/public-smoke-test.py --store-url http://localhost
```

`--local` accepts `storeDomain: "localhost"`, is compose-only, and serves plain HTTP
because a local name has no public DNS and no certificate. It must never be used for
a real store.

If the merchant supplies the identifiers and key here, you may run the preview
yourself; put them only in the 0600 file the generator writes. Chat-based agent
sessions usually have no Docker daemon and no registry access. When that applies,
say so plainly, hand the merchant the commands, and wait for their result rather
than reporting untested checks as passing.

## Licensing of customized output

The customized source remains under Apache License 2.0 for the Ping Business-originated code. Include copies of `LICENSE`, `NOTICE`, `TRADEMARKS.md`, and `THIRD_PARTY_NOTICES.md` in the delivered package. Document which files were changed. Merchant-supplied assets may retain separate ownership or license terms and must not be falsely relicensed.
