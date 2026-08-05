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
10. Deploy a merchant-supplied UI only. `source/merchant-store/` is a reference
    implementation carrying demonstration branding; it is what a customization
    starts from, not what customers see. `uiSource.mode` is `git` for any managed
    platform, or `local` with an absolute `uiSource.path` for Compose. The
    generator rejects an input that points back at the kit's own tree. If the
    merchant has only a ZIP and the target is a managed platform, stop and have
    them publish it to a repository — do not substitute the kit's UI.

## Supported platforms

Use the relevant adapter:

- Compose: `deployment/compose/`
- Northflank: `deployment/northflank/`
- Railway: `deployment/railway/`

A merchant who wants to run the store on their own server or VPS uses the Compose
adapter with a real public hostname. `deployment/SELF_HOSTING.md` is the
authoritative runbook for that path: it covers the server prerequisites, the DNS
record, the open ports, automatic Let's Encrypt issuance through Caddy, and the
backup duty the merchant takes on. Walk the merchant through those prerequisites
and confirm each one before generating anything — a missing DNS record or a
closed port 80 fails at certificate issuance, long after the point where it is
cheap to fix.

## Declare your capabilities first

Before collecting merchant values, state which of these you can actually do in
the current session: retrieve this kit, run `python3`, run shell commands on the
target machine, and call the selected platform's API. Many assistants can do none
of them, and no assistant can reach a merchant's private server.

If you cannot retrieve the kit, that is the first thing to say, not something to
work around. Ask the merchant to download the release archive named in
`kit-metadata.json` and attach it, or to paste the specific files you need. An
architecture recalled from training data is not the reviewed architecture, and
the merchant has no way to tell the difference until the deployment misbehaves.

When you cannot do a step, say so and switch to guiding: give the merchant exact
copy-pasteable commands and exact console steps, one at a time, wait for the
output, and continue from there. `scripts/prepare-deployment.py` needs only
Python 3 and the standard library, so a merchant can always run it themselves.

Never invent the generated secrets in conversation as a workaround. The generator
exists so that `ESTORE_CLIENT_SECRET`, the Keycloak admin password, and the
database password are written to `0600` files instead of into a chat transcript.
Never report a step as completed without output you actually saw.

`platform` and `pingbusinessEnvironment` are independent. `platform` selects where
the stack runs; `pingbusinessEnvironment` selects which Ping Business backend it
talks to and is always `staging` or `production`. There is no third environment,
and `localhost` is never an environment value — a local preview is
`platform: "compose"` with `--local`, and it still uses the real staging or
production backend and the merchant's real credentials.

For a local preview, `storeDomain` is `localhost`, region and DNS mode do not
apply, and no TLS certificate is obtainable. Do not request a DNS hostname, a
region, DNS records, or certificates. The merchant API key belongs only in the
0600 private env file the generator writes — a local run has no platform secret
store, which does not make the key any less sensitive.

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