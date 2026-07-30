#!/bin/sh
set -eu
D=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$D/../.." && pwd)
ENV_FILE=${1:-"$ROOT/.generated/compose.env"}
[ -f "$ENV_FILE" ] || { echo "Missing env file: $ENV_FILE" >&2; exit 2; }
docker compose --env-file "$ENV_FILE" -f "$D/compose.yaml" config >/dev/null
echo "PASS: Compose configuration is valid."
