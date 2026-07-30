# DNS and TLS automation

The default deployment uses one hostname:

```text
shop.example.com -> public edge service
```

The edge serves the UI and routes `/api` and `/auth` to private services.

## Automatic mode

Use a token restricted to the merchant's DNS zone and DNS-edit permission only.
The agent should:

1. discover/confirm the authoritative zone;
2. create any platform ownership-validation record;
3. create or update the single CNAME/A/AAAA record;
4. poll authoritative and public resolvers;
5. link/request the managed certificate;
6. verify hostname, chain, expiry, HTTPS, `/api/health`, and `/auth` behavior;
7. preserve prior records until a migration passes.

Never request a registrar-wide password when a zone-scoped token is available.

## Manual mode

Return an exact table such as:

| Host | Type | Value/target | Purpose | Status |
|---|---|---|---|---|
| `shop.example.com` | CNAME/A | platform target | UI, `/api`, `/auth` | pending |

Include any ownership-validation TXT record. Continue after resolution is
visible to the hosting platform.

## Cutover safety

Before replacing existing DNS, record the old value and TTL, establish rollback,
obtain merchant authorization, and keep the prior service available until the
new deployment passes.

## Completion criteria

- one valid certificate covers the requested hostname;
- renewal is managed;
- HTTP redirects to HTTPS where applicable;
- Keycloak-generated links use `https://<host>/auth`;
- checkout return/notification URLs derive from `https://<host>/api`;
- no private service is directly reachable.
