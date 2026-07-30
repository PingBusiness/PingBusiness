# Instructions for coding and infrastructure agents

Determine the requested workflow first:

- **Design/customize/rebrand UI** — read `design/DESIGN_AGENT.md`, then `prompts/DESIGN_PROMPT.md`.
- **Deploy/host/provision** — read `deployment/DEPLOY_AGENT.md`, then `prompts/DEPLOY_PROMPT.md`.
- **Both** — complete and validate design first, then deploy the resulting UI source.

## Universal rules

1. Treat `source/merchant-store/` as the canonical UI bundled in this kit.
2. Treat `source/estore-app/app.py` and `docs/ESTORE_APP_API_SPEC.md` as authoritative for API behavior.
3. Never use or restore an obsolete `/estore-ui` tree from another package.
4. Never place server secrets in browser source, runtime config, build arguments, assets, source maps, logs, screenshots, or public reports.
5. The browser calls only same-origin `/api`; it never calls central `biz-app`, PostgreSQL, Keycloak administration APIs, or PaymentAsia directly.
6. Preserve authentication, refresh, catalogue, inventory, checkout, recurring subscription, order, and payment-read behavior. Do not invent endpoints.
7. Use included schemas/templates/scripts. Prose explains intent and does not authorize a different security architecture.
8. Keep Keycloak brute-force protection disabled unless the merchant explicitly requests and approves a change.
9. Store generated credentials in protected platform controls. Public reports list names, locations, and rotation steps—not values.
10. Obtain explicit authorization before destructive work, DNS cutover, replacing a deployment, or enabling live payments.
11. Run the relevant acceptance checks and report actual evidence. Never infer success from a running-container icon alone.
12. Preserve `LICENSE`, `NOTICE`, `TRADEMARKS.md`, and applicable third-party notices in redistributed or customized source packages; identify modified files as required by Apache-2.0.

## Canonical public repository

- Repository: `https://github.com/PingBusiness/PingBusiness`
- Branch: `main`
- Kit root: `/merchant-store-vibe-coding-kit`
- Agent entrypoint: `https://raw.githubusercontent.com/PingBusiness/PingBusiness/main/merchant-store-vibe-coding-kit/AGENTS.md`

Clone the repository root when a platform requires Git source, then set its build/root path to the kit root above.

## Public repository behavior

Retrieve this public repository yourself. Do not ask a merchant to download and
re-upload files that are already public. Pin the exact commit used in every
design or deployment report.


## Supported deployment platforms

Deployment agents may use the platform adapter requested by the merchant:

- `deployment/qovery/`
- `deployment/northflank/`
- `deployment/railway/`
- `deployment/coolify/`
- `deployment/compose/` for local/reference deployments

Merchant-facing deployment forms must ask for `staging` or `production`, not a free-form `BIZ_APP_BASE_URL`. The generator maps the selected environment to the correct Ping Business endpoint.

## Output contracts

A design workflow returns a complete source tree and `DESIGN_REPORT.md`.

A deployment workflow returns:

- `https://<store-domain>`;
- API base `https://<store-domain>/api`;
- Keycloak base `https://<store-domain>/auth` and protected admin URL;
- platform project/environment/resource identifiers;
- DNS and certificate status;
- deployment, bootstrap, and smoke-test status;
- backup/restore status;
- protected secret locations and rotation instructions;
- no raw secret values in the public report.
