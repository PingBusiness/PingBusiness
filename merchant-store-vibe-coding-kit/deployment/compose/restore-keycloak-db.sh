#!/bin/sh
set -eu
[ "${CONFIRM_RESTORE:-}" = "yes" ] || {
  echo "Refusing destructive restore. Set CONFIRM_RESTORE=yes after verifying the target deployment." >&2
  exit 2
}
[ "$#" -ge 1 ] || { echo "Usage: CONFIRM_RESTORE=yes $0 BACKUP.sql.gz [ENV_FILE]" >&2; exit 2; }
BACKUP=$1
D=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$D/../.." && pwd)
ENV_FILE=${2:-"$ROOT/.generated/compose.env"}
[ -f "$BACKUP" ] || { echo "Missing backup: $BACKUP" >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "Missing env file: $ENV_FILE" >&2; exit 2; }

docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" stop edge estore-app keycloak
gzip -dc "$BACKUP" | docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" exec -T postgres \
  sh -ec 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" up -d --wait keycloak
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" run --rm keycloak-realm-bootstrap
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" up -d estore-app merchant-store edge
