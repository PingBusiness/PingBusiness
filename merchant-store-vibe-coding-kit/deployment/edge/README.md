# Single-host edge

The edge is the only public application service. It exposes one merchant host:

- `/` -> merchant-store UI
- `/api/*` -> private `estore-app`, with `/api` stripped
- `/auth/*` -> private Keycloak, with `/auth` stripped

PostgreSQL, Keycloak ports `8080`/`9000`, `estore-app:5000`, and the UI container are never published directly.

`Caddyfile.compose` terminates TLS itself. `Caddyfile.platform` listens on HTTP port `8080` because Qovery or Northflank terminates and manages TLS.

## Product image caching

Product images are served at `/api/image/<file_id>`. They are immutable: an
approved product's files can no longer change, and a replacement image is a new
`file_id`. A long, immutable lifetime therefore cannot serve stale bytes.

`estore-app` relays biz-app's response headers verbatim
(`proxy_binary_response`), and biz-app sends `Cache-Control: no-cache`. Left
alone, every image is revalidated over the network on every page view — a
measurable cost, since catalogue images run to several MB.

`routes.caddy` therefore overrides the header for that one path:

```
Cache-Control: public, max-age=31536000, immutable
```

Notes for anyone changing this:

- The image handler **must stay above** the general `@api` handler. Caddy
  evaluates `handle` blocks in source order and they are mutually exclusive.
- Use the bare `header_down Cache-Control "..."` form, which is a *set*. Do not
  pair it with `header_down -Cache-Control`: Caddy applies deletions after sets,
  so the pair removes the header entirely and responses end up with no caching
  directive at all.
- The path matcher is `^/api/image/[0-9]+$`. Non-numeric paths fall through to
  the ordinary `/api/*` handler and keep `no-cache`, as do all other API routes.
- The endpoint requires no customer authorization, so shared caches may store
  it. Do not copy this pattern onto any route guarded by `@customer_required`.

### Shared caching

Caddy has no built-in response cache — there is no equivalent of nginx's
`proxy_cache` / `proxy_cache_path` in a stock build. Caching therefore happens
in two places that the header above enables for free:

1. **The visitor's browser** — repeat views cost no request at all. This is the
   largest single win and needs nothing beyond the header.
2. **The platform CDN** — Railway, Qovery, Northflank, and a Coolify proxy all
   honour `Cache-Control` and will serve shared hits from their edge.

If a self-hosted shared cache is genuinely required (for example Compose with no
CDN in front), Caddy must be rebuilt with a cache module rather than
reconfigured:

```dockerfile
FROM caddy:2.11.4-builder AS builder
RUN xcaddy build --with github.com/caddyserver/cache-handler
FROM caddy:2.11.4-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

That adds `cache` as a usable directive, with its own store, TTL, and
stale-while-revalidate settings. It is deliberately **not** enabled by default:
it changes the edge image from a stock upstream build to a custom one, and the
browser plus CDN tiers already cover the common deployment shapes.
