# PingBusiness Merchant Store Vibe Coding Kit

This Apache-2.0-licensed public kit supports two low-friction merchant workflows:

1. **Customize** the canonical Angular merchant-store UI with an AI coding agent.
2. **Deploy** PostgreSQL, Keycloak, the ESTORE realm, `estore-app`, the selected
   UI, the private service network, one public edge, DNS/TLS, backups, and
   verification through a supported infrastructure platform.

## Public location

```text
Repository:       https://github.com/PingBusiness/PingBusiness
Kit directory:    merchant-store-vibe-coding-kit/
Kit page:         https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit
Agent entrypoint: https://raw.githubusercontent.com/PingBusiness/PingBusiness/main/merchant-store-vibe-coding-kit/AGENTS.md
```

Agents should retrieve the public repository themselves. Merchants should not
need to clone Git, edit YAML, or understand Docker, Keycloak, PostgreSQL,
reverse proxies, or certificate automation.

## Merchant workflow

### 1. Customize the UI

Open `website/pingbusiness-store-launcher.html`, complete the **Customize UI**
form, copy the generated prompt, and give it—along with logos and other assets—to
ChatGPT, Claude, Codex, Cursor, or another capable coding agent. The agent reads
this kit and returns a complete buildable customized UI package or repository.

### 2. Deploy the store

Open the **Deploy store** tab, choose Railway, Northflank, or your own server,
select staging or production, and provide the store domain and PingBusiness
merchant/store identifiers. The generated prompt deliberately excludes the
merchant API key. The deployment agent requests that key only when it can place
it directly into the selected platform's protected secret system.

The environment selection deterministically maps to:

```text
staging    -> https://biz-app.staging.pingbusiness.org
production -> https://biz-app.pingbusiness.org
```

## Default public topology

```text
Customers
   |
   v
https://shop.example.com              public edge only
   |-- /                              private merchant-store UI
   |-- /api/*                         private estore-app; /api stripped
   +-- /auth/*                        private Keycloak; /auth stripped

Private network
   estore-app ----> Keycloak ----> PostgreSQL
       |
       +---- HTTPS ----> central PingBusiness biz-app
```

Only the edge is public. The browser calls same-origin `/api` and never receives
merchant credentials, the merchant API key, the Keycloak client secret,
database credentials, or central PingBusiness authentication headers.

## Supported deployment targets

| Target | Adapter |
| --- | --- |
| Railway | `deployment/railway/` |
| Northflank | `deployment/northflank/` |
| Merchant's own server or VPS | `deployment/compose/`, per `deployment/SELF_HOSTING.md` |
| Local preview | `deployment/compose/` with `--local` |

All managed-platform adapters clone `https://github.com/PingBusiness/PingBusiness` at branch `main` and
use `/merchant-store-vibe-coding-kit` as the source root for bundled services.

## Important files

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Primary instructions for coding and deployment agents. |
| `website/pingbusiness-store-launcher.html` | Static design/deployment prompt generator. |
| `design/` and `prompts/DESIGN_PROMPT.md` | UI customization workflow and constraints. |
| `deployment/` and `prompts/DEPLOY_PROMPT.md` | Deployment schemas, adapters, prompts, and tests. |
| `source/merchant-store/` | Reference merchant UI with runtime `/api` configuration. Customization starts here; deployments build your customized copy, never this tree. |
| `source/estore-app/` | Canonical merchant-hosted Flask backend. |
| `keycloak/` | Portable ESTORE realm and idempotent provisioning utilities. |
| `github/merchant-store-vibe-kit-validate.yml` | Monorepo-aware CI workflow copied to repository-root `.github/workflows/`. |
| `PUBLISHING.md` | Exact monorepo and GitHub Release publication instructions. |
| `kit-metadata.json` | Machine-readable canonical repository, release, environment, and platform metadata. |
| `LICENSE`, `NOTICE`, `TRADEMARKS.md` | Apache-2.0 licensing and trademark boundaries. |

## Local validation

From `merchant-store-vibe-coding-kit/`:

```bash
./scripts/validate.sh
```

For a local Compose reference deployment:

```bash
python3 scripts/prepare-deployment.py \
  --input deployment/deployment-input.example.json \
  --output-dir .generated

docker compose \
  --env-file .generated/compose.env \
  -f deployment/compose/compose.yaml \
  up --build -d
```

## License and service boundary

Original kit content is licensed under Apache License 2.0. Merchants may use,
modify, and redistribute the merchant store and `estore-app`, including for
commercial deployments, subject to that license and third-party notices.

The license does not provide access to the hosted PingBusiness `biz-app`, a
merchant account, payment processing, or PingBusiness trademarks. Those remain
subject to separate credentials, service terms, and trademark permissions. See
`TRADEMARKS.md` and `THIRD_PARTY_NOTICES.md`.

## Release status

Version `1.0.0-rc3` is publication-ready as a **release candidate**: licensing
and public GitHub paths are resolved and static validation is included. It is
not yet live-certified across every platform. Do not advertise a platform as
one-click production-ready until its live deployment, DNS/TLS, checkout, and
backup-restore gates in `RELEASE_CHECKLIST.md` have passed.
