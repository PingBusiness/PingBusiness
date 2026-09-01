# Backup and restore

## What must be backed up

The merchant deployment's primary persistent state is the Keycloak PostgreSQL database. Also retain:

- deployment input with secret references, not public secret values;
- platform/IaC state in a protected backend;
- the exact kit and customized UI commit/image digest;
- DNS configuration and platform resource IDs;
- a redacted deployment report.

Central product/order/payment data is maintained by PingBusiness and is not stored in this merchant PostgreSQL instance.

## Backup policy

Recommended production baseline:

- automated daily database backup;
- at least 14 daily restore points;
- a longer monthly retention appropriate to the merchant's policy;
- encryption at rest and in transit;
- backup-failure alerts;
- restore testing at least quarterly and before major upgrades.

## Compose reference

Use `deployment/compose/backup-keycloak-db.sh` to create an encrypted-storage-ready PostgreSQL dump file on the operator host. Move it immediately to protected off-host storage. The script does not itself provide encryption or remote retention.

## Restore test

1. Create a clean isolated PostgreSQL/Keycloak environment.
2. Restore the database dump or managed snapshot.
3. Start the exact compatible Keycloak image.
4. Run `keycloak/realm-bootstrap/verify_realm.py` through the realm-bootstrap job image.
5. Test a non-production customer login/refresh.
6. Verify user count/realm/client and record the evidence.
7. Destroy the temporary restore environment securely.

## Disaster recovery

A recovery record should contain:

- last successful backup timestamp;
- backup location/snapshot ID;
- Keycloak image version;
- database engine/version;
- kit/UI commit or image digest;
- DNS records;
- platform project/environment IDs;
- secret-manager paths and authorized recovery contacts.

Do not place raw passwords or API keys in the recovery document.
