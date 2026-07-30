# Coolify deployment adapter

This adapter targets merchants who want Ping Business deployed on their own VPS or server managed by Coolify.

Coolify treats the Docker Compose file as the source of truth. It automatically detects variables referenced in the Compose file and can require them before deployment. Services with no mapped host port and no assigned domain remain private on the stack network. The only public service in this adapter is `edge`, which listens on container port `8080` and routes `/`, `/api/*`, and `/auth/*` to the private UI, `estore-app`, and Keycloak services.

Use repository `https://github.com/PingBusiness/PingBusiness`, branch `main`, and Compose file `/merchant-store-vibe-coding-kit/deployment/coolify/compose.yaml`.

## Merchant-visible flow

1. Create or select a Coolify project, server, and environment.
2. Create a Docker Compose resource from this public vibe-kit repository.
3. Use `deployment/coolify/compose.yaml` as the Compose file.
4. Set the domain for the `edge` service to `https://<store-domain>:8080` or assign the domain in the Coolify UI to service `edge` on container port `8080`.
5. Fill all required variables shown by Coolify.
6. Run the deployment.
7. Run the public smoke tests from `scripts/public-smoke-test.py`.

## Generated inputs

Run:

```sh
python3 scripts/prepare-deployment.py   --input deployment-input.json   --repository-url https://github.com/PingBusiness/PingBusiness   --repository-root-path /merchant-store-vibe-coding-kit   --output-dir .generated
```

For `platform: "coolify"`, the helper writes:

- `.generated/coolify/environment.secret.env` - variables to paste into Coolify, including generated secrets.
- `.generated/coolify/deployment-plan.json` - non-secret deployment plan.
- `.generated/coolify/api-request-body.secret.json` - optional API body skeleton for an agent using Coolify's API.

Do not commit `.generated/`.

## Ping Business environment

The merchant selects only `staging` or `production`. The deployment helper derives `BIZ_APP_BASE_URL`:

- `staging` -> `https://biz-app.staging.pingbusiness.org`
- `production` -> `https://biz-app.pingbusiness.org`

There is no merchant-facing arbitrary biz-app URL field.

## Public exposure rule

Only the Coolify proxy and the `edge` service may be public. PostgreSQL, Keycloak, realm bootstrap, `estore-app`, and `merchant-store` must stay private to the Compose stack.
