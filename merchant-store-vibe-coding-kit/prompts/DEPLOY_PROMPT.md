# Master deployment prompt

## Canonical public source

Clone `https://github.com/PingBusiness/PingBusiness` at branch `main`. The kit is not the repository root; it is located at `/merchant-store-vibe-coding-kit`. The browser-facing tree URL `https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit` is for navigation and must not be used as a Git clone URL. Pin the exact commit deployed in the final report.
Deploy a Ping Business merchant store using the public vibe coding kit repository supplied by the merchant.

You must follow `deployment/DEPLOY_AGENT.md` in the kit.

Collect only these merchant-facing values:

- hosting platform: Northflank, Railway, the merchant's own server (Compose with a real hostname, per `deployment/SELF_HOSTING.md`), or the local Compose preview
- Ping Business environment: staging or production
- store domain
- merchant identifier
- store identifier
- customized UI source, if any
- DNS mode and region, if required by the platform

Do not ask the merchant for a free-form `BIZ_APP_BASE_URL`. Derive it:

- staging -> `https://biz-app.staging.pingbusiness.org`
- production -> `https://biz-app.pingbusiness.org`

Do not ask the merchant to paste the merchant API key into the prompt. When deployment reaches the platform secret-creation step, request the key securely and store it directly as the platform secret `PINGBIZ_MERCHANT_API_KEY`. For a self-hosted deployment the equivalent location is the private `0600` environment file the generator writes on the merchant's server.

State up front which of kit retrieval, `python3`, shell access, and platform API access you actually have. If you lack any of them, guide the merchant through those steps with exact commands and wait for their output instead of reporting work you did not do.

If you cannot retrieve the kit at all, say so first and ask the merchant to attach the release archive from `kit-metadata.json` or the specific files you need. Never reconstruct the kit from memory.

Deploy PostgreSQL, Keycloak, the ESTORE realm/client, `estore-app`, the merchant-store UI, the edge router, DNS/TLS, and run the public smoke tests. Report the final storefront URL and verification result.