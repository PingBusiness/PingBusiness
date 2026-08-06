# Docker Compose reference deployment

This is the platform-neutral executable reference and the self-hosting target. It exposes only the `edge` service on ports 80/443. PostgreSQL, Keycloak, `estore-app`, and the UI remain on the private Compose network.

To run a real store on your own server or VPS, follow `deployment/SELF_HOSTING.md`
first — it covers the server, DNS, port, and certificate prerequisites that this
file assumes are already in place.

## Prepare

1. Point the intended `storeDomain` DNS record at the Docker host, or use a temporary test domain.
2. Copy `deployment/deployment-input.example.json` and replace every placeholder.
3. Generate private values:

```bash
python3 scripts/prepare-deployment.py \
  --input my-deployment.json \
  --output-dir .generated
```

## Local preview

To run the stack on your own machine — to look at a customized store before
deploying it anywhere — set `storeDomain` to `localhost` and pass `--local`:

```bash
python3 scripts/prepare-deployment.py \
  --input my-deployment.json \
  --local \
  --output-dir .generated

cd deployment/compose
MERCHANT_STORE_BUILD_CONTEXT=/path/to/customized/merchant-store \
  docker compose --env-file ../../.generated/compose.env -f compose.yaml up --build -d
```

The store is served at `http://localhost`. Verify it with:

```bash
python3 scripts/public-smoke-test.py --store-url http://localhost
```

`--local` serves plain HTTP on port 80 and skips ACME, because a local hostname has
no public DNS and no obtainable certificate. It is rejected for any platform other
than compose and for any hostname other than `localhost`, `127.0.0.1`, or a
`*.localhost` name. Never use it for a real store.

Tear down with `docker compose -p <project> down -v`. Note that the generator mints
a new `KEYCLOAK_DB_PASSWORD` on every run: if you regenerate `compose.env` while an
older `keycloak-postgres-data` volume still exists, Keycloak will fail to start with
`password authentication failed for user "keycloak"`. Drop the volume, or carry the
previous `KEYCLOAK_DB_*` values forward.

## Deploy

```bash
deployment/compose/deploy.sh .generated/compose.env
```

Caddy serves one origin:

- `https://<store-domain>/` -> UI
- `https://<store-domain>/api/*` -> `estore-app`
- `https://<store-domain>/auth/*` -> Keycloak

## Customized UI

Every deployment builds a merchant-supplied UI. The kit's `source/merchant-store` tree is the reference implementation a customization starts from, not a deployable storefront, and the generator rejects an input that points back at it.

For a public Git repository, set `uiSource.mode` to `git`; the generated Compose environment uses Docker's Git build context. For a private repository or a ZIP from a design agent, put the tree on the machine running Compose and use `uiSource.mode` `local` with an absolute `uiSource.path`; the generator writes it into `MERCHANT_STORE_BUILD_CONTEXT`.

## Backup and restore

```bash
deployment/compose/backup-keycloak-db.sh .generated/compose.env
CONFIRM_RESTORE=yes deployment/compose/restore-keycloak-db.sh BACKUP.sql.gz .generated/compose.env
```

A restore is destructive and must be tested in a non-production deployment first.
