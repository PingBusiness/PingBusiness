# Merchant-store design report

## Source

- Vibe-kit repository and pinned commit:
- Canonical/customized UI repository and pinned commit:
- Design date:

## Merchant direction

- Store/brand name:
- Design goals:
- Approved colours and typography:
- Supplied assets and rights notes:
- Layout/content decisions:

## Implemented changes

Describe changed routes, components, styles, assets, copy, and responsive
behavior. State explicitly that the runtime `ESTORE_APP_PUBLIC_URL` contract was
preserved.

## Functional invariants

Record evidence for authentication/refresh, catalogue, inventory, cart,
ordinary checkout, recurring subscription, authoritative status polling,
orders, and payments.

## Validation evidence

| Check | Command/environment | Result | Evidence |
|---|---|---|---|
| Clean install | `npm ci` | | |
| Production build | `npm run build:prod` | | |
| Frontend secret scan | `scripts/scan-frontend-secrets.py` | | |
| Runtime API injection | | | |
| Responsive/accessibility | | | |
| Checkout and subscription | | | |

## Deployment handoff

- UI repository/image/source package:
- Dockerfile path:
- Container port: `80`
- Health endpoint: `/healthz`
- Runtime variable: `ESTORE_APP_PUBLIC_URL=/api`
- Remaining merchant decisions:
