# Deployment workflow

Use `scripts/prepare-deployment.py` to validate merchant inputs and generate platform-specific values in `.generated/`.

Supported platforms:

- `compose`
- `qovery`
- `northflank`
- `railway`
- `coolify`

Merchant-facing input must ask for `pingbusinessEnvironment` with only these choices:

- `staging`
- `production`

The generator derives `BIZ_APP_BASE_URL` internally and writes it to the target platform configuration.

Do not include `PINGBIZ_MERCHANT_API_KEY` in a prompt, URL, markdown file, browser local storage, repository file, or deployment log. For static prompt-generator flows, tell the infrastructure agent to request the key only at the moment it creates the platform secret.
