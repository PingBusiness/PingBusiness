# Ping Business merchant-store deployment agent instructions

## Canonical public source

Clone `https://github.com/PingBusiness/PingBusiness` at branch `main`. The kit is not the repository root; it is located at `/merchant-store-vibe-coding-kit`. The browser-facing tree URL `https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit` is for navigation and must not be used as a Git clone URL. Pin the exact commit deployed in the final report.
You are deploying a Ping Business merchant store from this public vibe coding kit.

## Mandatory constraints

1. Use the public kit repository as the authoritative source.
2. Deploy exactly one public hostname: `https://<store-domain>`.
3. Route `/` to the merchant-store UI, `/api/*` to `estore-app`, and `/auth/*` to Keycloak.
4. Keep PostgreSQL, Keycloak, realm bootstrap, `estore-app`, and merchant-store private. Only the edge service may be public.
5. Ask the merchant to select only `staging` or `production`. Do not ask for a free-form Ping Business biz-app URL.
6. Derive `BIZ_APP_BASE_URL` from the selected environment:
   - `staging`: `https://biz-app.staging.pingbusiness.org`
   - `production`: `https://biz-app.pingbusiness.org`
7. Do not put `PINGBIZ_MERCHANT_API_KEY` in prompts, URLs, source files, generated markdown, or logs. Request it only when creating the selected platform's secret.
8. Keep Keycloak brute-force protection disabled for this version.
9. Run platform-specific health checks and the public smoke test before reporting success.

## Supported platforms

Use the relevant adapter:

- Compose: `deployment/compose/`
- Qovery: `deployment/qovery/`
- Northflank: `deployment/northflank/`
- Railway: `deployment/railway/`
- Coolify: `deployment/coolify/`

## Input preparation

After collecting merchant values and creating/receiving the merchant API key securely, create a private JSON file matching `deployment/deployment-input.schema.json` and run:

```sh
python3 scripts/prepare-deployment.py --input deployment-input.json --output-dir .generated
```

For managed platforms, pass the final published kit repository URL:

```sh
python3 scripts/prepare-deployment.py   --input deployment-input.json   --repository-url https://github.com/PingBusiness/PingBusiness   --repository-root-path /merchant-store-vibe-coding-kit   --output-dir .generated
```

The `.generated/` directory contains secrets and must not be committed.