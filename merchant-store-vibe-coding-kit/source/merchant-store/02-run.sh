#!/bin/sh
set -eu
: "${ESTORE_APP_PUBLIC_URL:=/api}"
docker network inspect pingbusiness-store >/dev/null 2>&1 || docker network create pingbusiness-store >/dev/null
docker run -d --restart unless-stopped --name merchant-store \
  --network pingbusiness-store \
  -e ESTORE_APP_PUBLIC_URL="$ESTORE_APP_PUBLIC_URL" \
  pingbusiness-merchant-store
