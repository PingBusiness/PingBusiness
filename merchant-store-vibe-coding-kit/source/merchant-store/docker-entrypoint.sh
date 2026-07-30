#!/bin/sh
set -eu

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

# The default production topology is same-origin: the browser calls /api and
# the edge routes that path privately to estore-app. A full HTTP(S) URL remains
# supported for deployments that deliberately use a separate API origin.
API_URL=${ESTORE_APP_PUBLIC_URL:-/api}

case "$API_URL" in
  /*)
    case "$API_URL" in
      //*) fail "ESTORE_APP_PUBLIC_URL must not be protocol-relative" ;;
    esac
    ;;
  http://*|https://*) ;;
  *) fail "ESTORE_APP_PUBLIC_URL must be root-relative or begin with http:// or https://" ;;
esac

if printf '%s' "$API_URL" | LC_ALL=C grep -q '[[:space:]]'; then
  fail "ESTORE_APP_PUBLIC_URL must not contain whitespace"
fi
if ! printf '%s' "$API_URL" | LC_ALL=C grep -Eq '^[ -~]+$'; then
  fail "ESTORE_APP_PUBLIC_URL must contain printable ASCII characters only"
fi
case "$API_URL" in
  *"'"*|*'"'*|*"\\"*|*'`'*|*'<'*|*'>'*)
    fail "ESTORE_APP_PUBLIC_URL contains unsupported characters"
    ;;
esac

# Avoid a double slash when services append routes such as /login.
if [ "$API_URL" != "/" ]; then
  while [ "${API_URL%/}" != "$API_URL" ]; do
    API_URL=${API_URL%/}
  done
fi

CONFIG_PATH=${PINGBUSINESS_RUNTIME_CONFIG_PATH:-/usr/local/apache2/htdocs/assets/runtime-config.js}
CONFIG_DIR=$(dirname "$CONFIG_PATH")
[ -d "$CONFIG_DIR" ] || fail "runtime-config directory does not exist: $CONFIG_DIR"

cat > "$CONFIG_PATH" <<EOF_CONFIG
window.__PINGBUSINESS_CONFIG__ = Object.freeze({
  apiUrl: '$API_URL'
});
EOF_CONFIG

exec "$@"
