#!/bin/bash
set -euo pipefail

: "${ESTORE_REALM:=ESTORE}"
: "${ESTORE_CLIENT_ID:=estore-app}"

if [[ -z "${ESTORE_CLIENT_SECRET:-}" ]]; then
  echo "ERROR: ESTORE_CLIENT_SECRET is required" >&2
  exit 2
fi

import_dir=/opt/keycloak/data/import
template=/opt/keycloak/data/ESTORE-realm-template.json
realm_file="${import_dir}/${ESTORE_REALM}-realm.json"

mkdir -p "$import_dir"
rm -f "$import_dir"/*-realm.json
cp "$template" "$realm_file"

exec /opt/keycloak/bin/kc.sh "$@"
