# Single-host edge

The edge is the only public application service. It exposes one merchant host:

- `/` -> merchant-store UI
- `/api/*` -> private `estore-app`, with `/api` stripped
- `/auth/*` -> private Keycloak, with `/auth` stripped

PostgreSQL, Keycloak ports `8080`/`9000`, `estore-app:5000`, and the UI container are never published directly.

`Caddyfile.compose` terminates TLS itself. `Caddyfile.platform` listens on HTTP port `8080` because Qovery or Northflank terminates and manages TLS.
