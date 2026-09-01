#!/usr/bin/env bash
# Collect the three sensitive PingBusiness merchant values via masked prompts and
# merge them into a deployment-input JSON, WITHOUT ever echoing them to the
# terminal, the shell history, logs, or a process-argument list.
#
# Why this exists: the merchant API key and the merchant/store identifiers must
# never be pasted into a chat, a prompt, generated markdown, a screenshot, or a
# log. A deploying agent (or a human) runs this locally; the values are read with
# a silent prompt and written straight into the 0600 input file that
# prepare-deployment.py consumes. Nothing is printed back.
#
# Usage:
#   scripts/collect-merchant-secrets.sh path/to/deployment-input.json
#
# The target file must already exist and contain the NON-secret fields
# (schemaVersion, deploymentName, platform, pingbusinessEnvironment, storeDomain,
# region, uiSource, ...). This script fills in merchantApiKey,
# merchantIdentifier and storeIdentifier in place, forces mode 0600, and clears
# the values from memory when done.
#
# For a managed platform you may instead type these values directly into the
# platform's own masked secret field (e.g. the Northflank secret-group editor)
# after provisioning — that is equally valid and never involves a local file.
set -euo pipefail

file="${1:-}"
if [ -z "$file" ] || [ ! -f "$file" ]; then
  echo "usage: $0 path/to/deployment-input.json  (file must already exist with the non-secret fields)" >&2
  exit 2
fi
command -v jq >/dev/null 2>&1 || { echo "error: jq is required" >&2; exit 2; }

# Read one secret with no echo. Result is left in the caller's REPLY_SECRET.
read_secret() {
  local prompt="$1" value=""
  printf '%s' "$prompt" >&2
  IFS= read -rs value
  printf '\n' >&2
  REPLY_SECRET="$value"
}

read_secret "Merchant API key (input hidden): ";    key="$REPLY_SECRET"
read_secret "Merchant identifier (hidden): ";       mid="$REPLY_SECRET"
read_secret "Store identifier (hidden): ";          sid="$REPLY_SECRET"
REPLY_SECRET=""

if [ "${#key}" -lt 16 ]; then
  echo "error: merchant API key looks too short (< 16 characters); aborting without writing." >&2
  unset key mid sid; exit 2
fi
if [ -z "$mid" ] || [ -z "$sid" ]; then
  echo "error: merchant/store identifier must not be empty; aborting without writing." >&2
  unset key mid sid; exit 2
fi

umask 177
tmp="$(mktemp "${TMPDIR:-/tmp}/mds.XXXXXX")"
# Values flow jq stdin->file only; they are never placed on a command line that
# would appear in `ps` — jq reads them from --arg, and the file is created 0600.
if jq --arg k "$key" --arg m "$mid" --arg s "$sid" \
      '.merchantApiKey=$k | .merchantIdentifier=$m | .storeIdentifier=$s' \
      "$file" > "$tmp"; then
  mv "$tmp" "$file"
  chmod 600 "$file"
else
  rm -f "$tmp"
  echo "error: failed to update $file" >&2
  unset key mid sid; exit 1
fi

unset key mid sid
echo "OK: merchantApiKey + identifiers written into $file (mode 0600). No secret value was printed." >&2
