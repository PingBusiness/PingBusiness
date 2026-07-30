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
9. Return the complete customized source tree.
10. Include `DESIGN_REPORT.md` with changed files, tokens, assets, commands/results, limitations, and deployment handoff.

## Deployment handoff

The customized UI must support:

```bash
docker build -t merchant-store-custom .
docker run --rm -e ESTORE_APP_PUBLIC_URL=/api -p 8080:80 merchant-store-custom
```

It must listen on port 80, answer `/healthz`, retain runtime config, and require
no compile-time store hostname. A customized repository must be suitable for an
agent to pass directly to Qovery or Northflank.

## Licensing of customized output

The customized source remains under Apache License 2.0 for the Ping Business-originated code. Include copies of `LICENSE`, `NOTICE`, `TRADEMARKS.md`, and `THIRD_PARTY_NOTICES.md` in the delivered package. Document which files were changed. Merchant-supplied assets may retain separate ownership or license terms and must not be falsely relicensed.
