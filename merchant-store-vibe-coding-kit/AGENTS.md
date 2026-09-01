# Instructions for coding and infrastructure agents

Determine the requested workflow first:

- **Design/customize/rebrand UI** — read `design/DESIGN_AGENT.md`, then `prompts/DESIGN_PROMPT.md`.
- **Deploy/host/provision** — read `deployment/DEPLOY_AGENT.md`, then `prompts/DEPLOY_PROMPT.md`.
- **Both** — complete and validate design first, then deploy the resulting UI source.

## Universal rules

1. Treat `source/merchant-store/` as the canonical reference UI: the starting
   point every customization begins from, and an example of the contracts a
   storefront must satisfy. It is never itself deployed. Every deployment builds
   a merchant-supplied UI, and `uiSource` has no mode that targets this tree.
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

Retrieve this public repository yourself whenever you can, by cloning it or by
fetching its files over the web. Do not make a merchant hand you files you are
able to obtain. Pin the exact commit used in every design or deployment report.

If you cannot retrieve it at all — no repository access, no file access, and no
web access, which is the normal situation for a chat-only assistant — say so
before doing anything else and ask the merchant to download the release archive
and attach it:

```text
https://github.com/PingBusiness/PingBusiness/releases/latest/download/pingbusiness-merchant-store-vibe-coding-kit.zip
```

Name the specific files you need if the whole archive is impractical to attach.

Never reconstruct this kit from memory. A plausible-looking Compose file, realm
template, or Angular storefront that does not match the real source fails only
after the merchant has deployed it, and rule 7 below exists precisely because a
remembered architecture is not the reviewed one. Asking for an attachment is
always correct when the alternative is guessing.


## Supported deployment platforms

Deployment agents may use the platform adapter requested by the merchant:

- `deployment/northflank/`
- `deployment/railway/`
- `deployment/compose/` for a local preview, and for self-hosting on a
  merchant-owned server per `deployment/SELF_HOSTING.md`

Merchant-facing deployment forms must ask for `staging` or `production`, not a free-form `BIZ_APP_BASE_URL`. The generator maps the selected environment to the correct PingBusiness endpoint.

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
