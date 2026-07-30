#!/bin/sh
set -eu
COMPOSE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$COMPOSE_DIR/../.." && pwd)
ENV_FILE=${1:-"$REPO_ROOT/.generated/compose.env"}
[ -f "$ENV_FILE" ] || { echo "Missing env file: $ENV_FILE" >&2; exit 2; }
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_DIR/compose.yaml" config >/dev/null
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_DIR/compose.yaml" up --build -d
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_DIR/compose.yaml" ps
