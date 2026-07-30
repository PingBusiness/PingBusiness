#!/bin/sh
set -eu
D=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$D/../.." && pwd)
ENV_FILE=${1:-"$ROOT/.generated/compose.env"}
BACKUP_DIR=${BACKUP_DIR:-"$D/backups"}
[ -f "$ENV_FILE" ] || { echo "Missing env file: $ENV_FILE" >&2; exit 2; }
mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/keycloak-$STAMP.sql.gz"
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" exec -T postgres \
  sh -ec 'exec pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "$OUT"
chmod 0600 "$OUT"
echo "$OUT"
