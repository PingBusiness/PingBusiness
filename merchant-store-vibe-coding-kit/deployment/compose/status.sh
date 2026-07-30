#!/bin/sh
set -eu
D=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$D/../.." && pwd)
ENV_FILE=${1:-"$ROOT/.generated/compose.env"}
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" ps
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" logs --tail=40 keycloak-realm-bootstrap estore-app edge
