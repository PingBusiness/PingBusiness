#!/bin/sh
set -eu
: "${ESTORE_ENV_FILE:=.env}"
docker network inspect pingbusiness-store >/dev/null 2>&1 || docker network create pingbusiness-store >/dev/null
docker run -d --restart unless-stopped --name estore-app \
  --network pingbusiness-store \
  --env-file "$ESTORE_ENV_FILE" \
  pingbusiness-estore-app
