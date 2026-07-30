#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

python3 scripts/validate-kit.py
python3 scripts/scan-frontend-secrets.py source/merchant-store
python3 - <<'PY'
import ast
from pathlib import Path
for base in (Path('scripts'), Path('keycloak/realm-bootstrap')):
    for path in sorted(base.rglob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('PASS: Python source syntax validation.')
PY

find scripts deployment/compose keycloak source/merchant-store -type f \( \
  -name '*.sh' -o -name 'docker-entrypoint.sh' -o -name 'container-entrypoint.sh' \
\) | while IFS= read -r file; do sh -n "$file"; done
bash -n keycloak/container-entrypoint.sh
scripts/test-ui-runtime-config.sh

if [ "${RUN_NETWORKED_UI_BUILD:-0}" = "1" ]; then
  (cd source/merchant-store && npm ci --no-audit --no-fund && npm run build:prod)
  python3 scripts/scan-frontend-secrets.py source/merchant-store/dist
fi

echo 'PASS: static kit validation completed.'
