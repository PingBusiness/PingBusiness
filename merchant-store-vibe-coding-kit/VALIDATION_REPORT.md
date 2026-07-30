# Ping Business Merchant Store Vibe Coding Kit validation report

**Version:** `1.0.0-rc3`  
**Validation date:** 2026-07-30

## Result

```text
16 deterministic kit checks passed
0 warnings
0 failures
```

Additional release checks completed successfully:

- canonical `estore-app/app.py`, `requirements.txt`, and ESTORE realm hashes;
- Apache-2.0 root and component-local license/notice integrity;
- canonical repository, branch, kit-root, raw-agent, and release metadata;
- JSON parsing and JSON Schema validation for deployment inputs;
- deployment-input generation for Compose, Railway, Coolify, Northflank, and
  Qovery using non-production dummy data;
- deterministic staging `BIZ_APP_BASE_URL` generation;
- mode `0600` on generated secret-bearing files;
- confirmation that generated credentials were not printed in command output;
- frontend server-secret-name scan;
- merchant-store runtime `/api` configuration positive and negative tests;
- Python syntax validation without packaging bytecode caches;
- shell syntax validation;
- GitHub Actions YAML parsing;
- launcher JavaScript syntax validation;
- headless-browser design/deployment prompt generation;
- production environment mapping to `https://biz-app.pingbusiness.org`;
- confirmation that the launcher has no API-key or editable-kit-URL field;
- responsive launcher overflow checks at 390, 768, and 1440 pixels;
- one-public-edge/static private-service checks for all platform adapters.

## Security and publication findings

- No live merchant API key, Keycloak client secret, database password,
  administrative password, DNS token, or platform token is included.
- The static launcher never collects `PINGBIZ_MERCHANT_API_KEY`; its deployment
  prompt instructs the agent to request the key only at the protected platform
  secret-creation step.
- `BIZ_APP_BASE_URL` is not merchant-editable. It is derived from exactly one of
  `staging` or `production`.
- Keycloak brute-force protection and permanent lockout remain disabled by the
  agreed product decision.
- The obsolete `/estore-ui` source is not present or used.
- The kit is monorepo-aware: managed platforms clone
  `https://github.com/PingBusiness/PingBusiness` and use
  `/merchant-store-vibe-coding-kit` as the kit root.

## Deliberately outstanding live gates

This release candidate has not yet claimed successful live deployment on every
third-party platform. Before a stable `1.0.0` release, complete the live gates
in `RELEASE_CHECKLIST.md`, including networked Angular and container builds,
real staging authentication/checkout tests, Railway/Coolify/Qovery/Northflank
deployments, DNS/TLS verification, private-port verification, and a tested
Keycloak PostgreSQL restore.
