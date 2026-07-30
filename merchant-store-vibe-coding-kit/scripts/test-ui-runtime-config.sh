#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENTRYPOINT="$ROOT/source/merchant-store/docker-entrypoint.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

run_ok() {
  expected=$1
  value=$2
  path="$TMP/runtime-config.js"
  ESTORE_APP_PUBLIC_URL="$value" PINGBUSINESS_RUNTIME_CONFIG_PATH="$path" "$ENTRYPOINT" true
  grep -Fq "apiUrl: '$expected'" "$path" || {
    echo "FAIL: expected $expected for input $value" >&2
    cat "$path" >&2
    exit 1
  }
}

run_fail() {
  value=$1
  path="$TMP/runtime-config.js"
  if ESTORE_APP_PUBLIC_URL="$value" PINGBUSINESS_RUNTIME_CONFIG_PATH="$path" "$ENTRYPOINT" true >/dev/null 2>&1; then
    echo "FAIL: unsafe value was accepted: $value" >&2
    exit 1
  fi
}

run_ok /api /api/
run_ok /api/v1 /api/v1///
run_ok https://shop.example.com/api https://shop.example.com/api/
run_fail //evil.example
run_fail 'javascript:alert(1)'
run_fail '/api bad'
run_fail "/api'bad"
run_fail '/api`bad'

echo 'PASS: merchant-store runtime configuration validation.'
