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

## Regressions AI customization has actually caused

Every item below was found in a customized store after it looked finished. They
are design-adjacent, so they survive a visual review; each one reached a real
merchant. Treat this as a checklist before returning a package.

**Change the design layer only.** Do not alter component structure, data flow,
routing, or scroll/overflow behaviour to achieve a visual result.

1. **The store name comes from the API.** Bind `store?.name` and leave it empty
   until it loads. A hardcoded name or fallback constant flashes the wrong brand
   on every reload before the real value arrives.
2. **Do not change overflow on list containers.** Keep any overflow scoped to the
   existing narrow-screen media query. Setting `overflow-x: auto`
   unconditionally coerces `overflow-y` to `auto`, which turns the wrapper into a
   scroll container, clips the absolutely-positioned row menu, and adds a
   spurious vertical scrollbar.
3. **Keep auth-state gating on every navigation element.** The header renders
   account and sign-out links behind `*ngIf="authState$ | async"` with a
   `#signedOut` template for the rest. A rebuilt header or bottom bar that drops
   that condition offers "Sign Up / Log In" to a customer who is already signed
   in.
4. **Never bind a form directly to a loaded model.** Edit a copy and assign it
   back only once the API confirms. Binding `[(ngModel)]` to the same object the
   page renders means every keystroke updates the page behind the dialog, so
   Cancel appears to save.
5. **Do not rewrite error handling around status codes you assume.** A wrong
   password is HTTP 400 with `{"error":"invalid_grant"}`, not 401, because
   `estore-app` forwards Keycloak's OAuth response verbatim. Keep the existing
   checks; if you touch them, verify against a real failing request.

If a design requirement seems to need one of these changed, say so and ask
rather than changing it silently.

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

## Design dev server

If your session can run commands, serve the customized UI as soon as it builds and
give the merchant a URL. It costs nothing, needs no Docker, no kit, and no merchant
credentials, and it turns the feedback loop from "package, hand off, wait" into
"refresh the tab":

```bash
cd <customized merchant-store>
npm ci
npm start          # ng serve --host 0.0.0.0
```

Report the URL the dev server actually printed — normally `http://localhost:4200`,
but Angular moves to another port when 4200 is taken, so do not assume it. Leave it
running across feedback rounds.

State its limits in the same breath, every time. There is no `estore-app` behind
it, so `APP_URL` falls back to `http://localhost:5000` and every API call fails:
the merchant sees layout, branding, typography, spacing, and responsive behaviour,
and sees nothing about the catalogue, login, or checkout. A merchant who is not
told this reads empty product lists as a design bug, or worse, as approval.

The dev server binds `0.0.0.0`. On a shared or cloud machine, tunnel it rather than
leaving it reachable.

This never replaces the packaged preview below. It is a look, not an approval.

## Local preview

Checks 2-8 below exercise the live catalogue, Keycloak and checkout. None of them
can run against a static build or against the dev server above, so bring the whole
stack up on the merchant's own machine and let the merchant look at the result
before anything is deployed.

The preview needs a running `estore-app`, which needs the merchant identifier, the
store identifier, and the merchant API key. Those are deliberately not part of the
design brief and must not be requested in the design conversation. So the design
step does not run the preview itself — it produces the package and hands off.

Deliver `HANDOFF.md` inside the package with the merchant's exact next step:

> Your customized store is in this package. To see it running on your own machine,
> open the launcher, go to the **Deploy store** tab, choose **Local preview (Docker
> Compose on my machine)** as the hosting platform, set UI source to **I will attach
> the customized UI ZIP**, fill in your merchant and store identifiers, and generate
> that prompt. Attach this package to the conversation. The agent will bring the
> stack up and give you a `http://localhost` address.

That prompt drives the commands below; reproduce them in `HANDOFF.md` so the merchant
can also run them directly. The package contains only the UI, so the first step is
obtaining the kit:

```bash
# the package ships the UI only; the stack comes from the kit
git clone https://github.com/PingBusiness/PingBusiness.git
cd PingBusiness/merchant-store-vibe-coding-kit

# storeDomain must be "localhost" and platform must be "compose"
python3 scripts/prepare-deployment.py --input deployment-input.json --local --output-dir .generated

# MERCHANT_STORE_BUILD_CONTEXT points at the unzipped customized source
cd deployment/compose
MERCHANT_STORE_BUILD_CONTEXT=/path/to/unzipped/merchant-store \
  docker compose --env-file ../../.generated/compose.env -f compose.yaml up --build -d

python3 ../../scripts/public-smoke-test.py --store-url http://localhost
```

`--local` is the only supported way to preview the full stack: it is compose-only, it accepts
`localhost` where a real deployment requires a public hostname, and it serves plain
HTTP because a local name has no DNS and therefore no certificate. Never use it for
a real store. Tear down with `docker compose -p <project> down -v`.

Treat this as a loop, not a gate. The merchant looks at `http://localhost`, comes
back with corrections, and you rebuild and reissue the package. Only once they are
happy with what they see should they move to a real deployment.

If the merchant does supply the identifiers and key in this conversation, you may run
the preview yourself. Put them only in the 0600 file the generator writes — never in
the Compose file, the UI, chat, logs, or `DESIGN_REPORT.md`. Most chat-based agent
sessions also have no Docker daemon and no container-registry access; if that is your
situation, say so plainly, hand over the commands, and wait for the merchant to report
back rather than reporting checks you did not run.

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

- the complete customized `source/merchant-store` tree, and nothing else from the kit;
- a production Dockerfile and unchanged runtime-config contract;
- `HANDOFF.md` with the local-preview step above, so the merchant can see the store
  running before committing to a deployment;
- `DESIGN_REPORT.md`;
- validation output;
- a concise list of any merchant decisions still required.

Do not stop at a mockup, image, patch snippet, or partial component.

Do not vendor a copy of the kit into the package. Ship the customized UI tree, the
legal files, `HANDOFF.md`, and `DESIGN_REPORT.md` — not `deployment/`, `keycloak/`,
`scripts/`, `prompts/`, `docs/`, `design/`, `website/`, or `source/estore-app`. The
merchant obtains those by cloning the kit, exactly as `HANDOFF.md` instructs, and
the preview points `MERCHANT_STORE_BUILD_CONTEXT` at the unzipped UI tree.

A vendored kit copy is not merely redundant. Every platform adapter clones the kit
from its published repository at deploy time, so edits a merchant makes to a
bundled `deployment/` directory silently do nothing, and a regenerated
`CHECKSUMS.sha256` destroys the provenance it exists to record.

## Licensing of customized output

The customized source remains under Apache License 2.0 for the Ping Business-originated code. Include copies of `LICENSE`, `NOTICE`, `TRADEMARKS.md`, and `THIRD_PARTY_NOTICES.md` in the delivered package. Document which files were changed. Merchant-supplied assets may retain separate ownership or license terms and must not be falsely relicensed.
