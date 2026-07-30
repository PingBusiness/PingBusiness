# Docker Compose reference deployment

This is the platform-neutral executable reference and a self-hosted fallback. It exposes only the `edge` service on ports 80/443. PostgreSQL, Keycloak, `estore-app`, and the UI remain on the private Compose network.

## Prepare

1. Point the intended `storeDomain` DNS record at the Docker host, or use a temporary test domain.
2. Copy `deployment/deployment-input.example.json` and replace every placeholder.
3. Generate private values:

```bash
python3 scripts/prepare-deployment.py \
  --input my-deployment.json \
  --output-dir .generated
```

## Deploy

```bash
deployment/compose/deploy.sh .generated/compose.env
```

Caddy serves one origin:

- `https://<store-domain>/` -> UI
- `https://<store-domain>/api/*` -> `estore-app`
- `https://<store-domain>/auth/*` -> Keycloak

## Customized UI

For a public Git repository, set `uiSource.mode` to `git`; the generated Compose environment uses Docker's Git build context. For a private repository, clone it locally and change `MERCHANT_STORE_BUILD_CONTEXT` in the private env file to the local directory.

## Backup and restore

```bash
deployment/compose/backup-keycloak-db.sh .generated/compose.env
CONFIRM_RESTORE=yes deployment/compose/restore-keycloak-db.sh BACKUP.sql.gz .generated/compose.env
```

A restore is destructive and must be tested in a non-production deployment first.
