# Master deployment prompt

## Canonical public source

Clone `https://github.com/PingBusiness/PingBusiness` at branch `main`. The kit is not the repository root; it is located at `/merchant-store-vibe-coding-kit`. The browser-facing tree URL `https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit` is for navigation and must not be used as a Git clone URL. Pin the exact commit deployed in the final report.
Deploy a Ping Business merchant store using the public vibe coding kit repository supplied by the merchant.

You must follow `deployment/DEPLOY_AGENT.md` in the kit.

Collect only these merchant-facing values:

- hosting platform: Qovery, Northflank, Railway, Coolify, or Compose reference
- Ping Business environment: staging or production
- store domain
- merchant identifier
- store identifier
- customized UI source, if any
- DNS mode and region, if required by the platform

Do not ask the merchant for a free-form `BIZ_APP_BASE_URL`. Derive it:

- staging -> `https://biz-app.staging.pingbusiness.org`
- production -> `https://biz-app.pingbusiness.org`

Do not ask the merchant to paste the merchant API key into the prompt. When deployment reaches the platform secret-creation step, request the key securely and store it directly as the platform secret `PINGBIZ_MERCHANT_API_KEY`.

Deploy PostgreSQL, Keycloak, the ESTORE realm/client, `estore-app`, the merchant-store UI, the edge router, DNS/TLS, and run the public smoke tests. Report the final storefront URL and verification result.