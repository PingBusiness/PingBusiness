# Operations guide

## Health endpoints

| Component | Endpoint | Expected |
|---|---|---|
| Merchant UI | `/healthz` | `200`, body `ok` |
| `estore-app` | `/health` | `200` JSON status |
| Keycloak management | private `:9000/health/ready` and `/health/live` | `200` |
| PostgreSQL | platform database health / `pg_isready` | ready |

Because `estore-app` resolves merchant/store scope during startup, a running healthy process also indicates that initial Ping Business scope validation succeeded.

## Monitoring

Alert on:

- service health failures and restart loops;
- Keycloak/database connection failures;
- repeated `401/403` from Ping Business scope calls;
- checkout callback/verification errors;
- certificate expiry/renewal failure;
- backup failure;
- unexpected public-port exposure;
- disk/storage growth.

## Logs

Use platform log collection with bounded retention. Redact secrets and tokens. Store correlation IDs, checkout IDs where safe, route/status, and high-level error categories.

## Secret rotation

### Merchant API key

Coordinate rotation with Ping Business. Update the secret store, restart/redeploy `estore-app`, verify scope, then revoke the old key.

### ESTORE client secret

Update Keycloak client and platform secret atomically or in a controlled two-step maintenance window. Run the realm verification job and login/refresh tests.

### Keycloak administrator password

Rotate through Keycloak/platform procedures and update the protected credential record. It is not used by normal `estore-app` requests.

### Database password

Follow the managed database rotation procedure and update Keycloak without exposing the value. Verify readiness before removing the old credential.

## Upgrades

1. Back up PostgreSQL and export/reconcile realm configuration.
2. Test the new kit commit in staging.
3. Review Keycloak, Python, Angular, and platform release notes.
4. Apply schema/config changes deterministically.
5. Run full authentication, catalogue, checkout, and subscription tests.
6. Retain a rollback image/commit and backup until stability is established.

Keycloak startup import skips an existing realm. Upgrades to realm settings therefore require an idempotent admin-API reconciliation step or an explicitly reviewed migration—not merely replacing the JSON file.
