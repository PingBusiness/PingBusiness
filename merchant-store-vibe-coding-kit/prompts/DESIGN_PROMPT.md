# Governing prompt: customize a Ping Business merchant store

You are the implementation agent for a production Ping Business merchant storefront.

Retrieve this repository yourself. Read `AGENTS.md`, `design/DESIGN_AGENT.md`, `docs/ESTORE_APP_API_SPEC.md`, `docs/MERCHANT_STORE_REFERENCE_ARCHITECTURE.md`, `docs/SECURITY.md`, and the complete `source/merchant-store/` tree before editing code.

## Objective

Create a complete, production-buildable, branded merchant-store application by customizing `source/merchant-store/` with the supplied merchant brief and assets. Preserve the current Ping Business API, authentication, token refresh, catalogue, inventory, ordinary checkout, recurring subscription, order, and payment-read behavior.

## Source authority

Use this order when requirements conflict:

1. current `docs/ESTORE_APP_API_SPEC.md` and `source/estore-app/app.py`;
2. working behavior in `source/merchant-store/`;
3. explicit merchant requirements;
4. accessible and secure defaults.

Never use an obsolete `estore-ui` tree from another repository.

## Non-negotiable security rules

- The UI calls only same-origin `/api` by default (or an explicitly approved public `estore-app` base URL).
- Keep `ESTORE_APP_PUBLIC_URL` as runtime configuration and use `/api` for the default pipeline; do not hard-code a production host in TypeScript.
- Never place merchant/store credentials, the Ping Business API key, Keycloak client secret, database credentials, or administrative credentials in frontend source, assets, build arguments, runtime config, logs, or reports.
- Never set Ping Business server-to-server headers in the browser.
- Never call central `biz-app`, PostgreSQL, Keycloak administration APIs, or PaymentAsia APIs directly from the browser.
- Do not use raw `innerHTML` for merchant content or arbitrary assets. Treat returned PaymentAsia/estore callback HTML only through the existing controlled checkout flow.
- Customer tokens remain sensitive browser session state. Do not log or transmit them to analytics.

## Functional invariants

Preserve all current routes and their capabilities:

- home and catalogue;
- product detail/media/download;
- cart and inventory revalidation;
- sign-up, sign-in, refresh, sign-out, account, and password change;
- ordinary cart checkout through `POST /checkout` using `response_mode: "json"` and the returned `action_url`/`fields` form-post launch;
- recurring single-product enrollment through `POST /subscribe`;
- authoritative completion only through authenticated `/checkout/status/{checkout_id}` polling;
- `postMessage` only as a wake-up hint, never proof of payment;
- orders, order items, subscriptions, and payments as customer-scoped reads;
- no client-created orders, payments, or inventory adjustments.

For ordinary checkout, keep the current popup/form-post strategy or a demonstrably equivalent controlled flow. For subscription HTML, retain the existing controlled popup/iframe fallback. Do not conflate the two response formats.

## Design implementation

- Convert merchant requirements into documented design tokens.
- Use semantic HTML, visible keyboard focus, meaningful labels, status announcements, and accessible contrast.
- Support 320, 375, 768, 1024, and 1440 pixel viewport checks.
- Design loading, empty, disabled, error, success, pending, timeout, and recovery states.
- Preserve logo proportions and asset rights restrictions.
- Do not ship inspiration-only assets.
- Keep performance reasonable: optimize images, lazy-load where appropriate, and avoid unnecessary third-party scripts.

## Required validation

Run and report:

```bash
npm ci
npm run build:prod
python3 ../../scripts/scan-frontend-secrets.py .
```

## Local preview

Checks 2-8 below exercise the live catalogue, Keycloak and checkout. None of them
can run against a static build, so bring the whole stack up on the merchant's own
machine first and let the merchant look at the result before anything is deployed.

Most chat-based agent sessions have no Docker daemon and no container-registry
access. If that is your situation, do not fake these checks and do not skip them
silently: generate the configuration, hand the merchant the two commands below,
and wait for them to report back.

```bash
# from the kit root, with the merchant's deployment-input.json (storeDomain: "localhost")
python3 scripts/prepare-deployment.py --input deployment-input.json --local --output-dir .generated

# MERCHANT_STORE_BUILD_CONTEXT points at the customized source you produced
cd deployment/compose
MERCHANT_STORE_BUILD_CONTEXT=/path/to/customized/merchant-store \
  docker compose --env-file ../../.generated/compose.env -f compose.yaml up --build -d
```

The store is then at `http://localhost`. Verify it with the kit's own smoke test:

```bash
python3 scripts/public-smoke-test.py --store-url http://localhost
```

`--local` is the only supported way to preview: it is compose-only, it accepts
`localhost` where a real deployment requires a public hostname, and it serves plain
HTTP because a local name has no DNS and therefore no certificate. Never use it for
a real store.

Treat this as a loop, not a gate. Show the merchant `http://localhost`, take their
corrections, rebuild, and show them again. Move on to the deployment prompt only
once they are happy with what they see. Tear down with
`docker compose -p <project> down -v` when finished.

Also test at minimum:

1. runtime API URL injection;
2. catalogue/product/inventory behavior;
3. registration/login/refresh/logout;
4. cart revalidation and currency handling;
5. ordinary checkout launch and authoritative status polling;
6. subscription launch and authoritative status polling;
7. order/payment read flows;
8. direct SPA-route refresh;
9. `/healthz`;
10. responsive and keyboard behavior.

Do not claim a test passed unless you ran it. Explain external-environment blockers precisely.

## Deliverables

Return:

- the complete customized source package;
- a production Dockerfile and unchanged runtime-config contract;
- `DESIGN_REPORT.md`;
- validation output;
- a concise list of any merchant decisions still required.

Do not stop at a mockup, image, patch snippet, or partial component.

## Licensing of customized output

The customized source remains under Apache License 2.0 for the Ping Business-originated code. Include copies of `LICENSE`, `NOTICE`, `TRADEMARKS.md`, and `THIRD_PARTY_NOTICES.md` in the delivered package. Document which files were changed. Merchant-supplied assets may retain separate ownership or license terms and must not be falsely relicensed.
