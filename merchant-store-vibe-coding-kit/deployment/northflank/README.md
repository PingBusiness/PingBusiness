# Northflank deployment adapter

`template.json` is a dynamic Northflank template for the complete Ping Business
merchant-store stack. It uses one public hostname and exposes only the edge
service:

```text
https://shop.example.com/       -> private merchant-store UI
https://shop.example.com/api/*  -> private estore-app
https://shop.example.com/auth/* -> private Keycloak
```

The workflow creates resources sequentially:

1. private PostgreSQL add-on;
2. private Keycloak service;
3. idempotent ESTORE realm/client bootstrap and verification job;
4. private `estore-app` service;
5. private default or customized merchant-store UI;
6. one public edge service linked to the merchant hostname.

Northflank clones `https://github.com/PingBusiness/PingBusiness` and receives `KIT_REPOSITORY_ROOT_PATH=/merchant-store-vibe-coding-kit`.

## Nontechnical merchant flow

The merchant supplies the public kit URL, the three Ping Business credentials,
one desired hostname, a region, and optionally a customized UI handoff. The
authorized deployment agent should:

1. retrieve this public repository;
2. authenticate with a narrowly scoped Northflank team token;
3. add and verify the merchant's domain at team level;
4. gather and validate `../deployment-input.schema.json`;
5. run `../../scripts/prepare-deployment.py`, which writes public arguments and
   private argument overrides without printing secrets;
6. import or create the template and run it with those overrides;
7. monitor every sequential condition and the realm-bootstrap `JobRun`;
8. configure the single DNS record automatically only when narrowly scoped DNS
   authorization was provided, otherwise display the exact record;
9. wait for the certificate and run public smoke tests;
10. return URLs, test status, backup status, and protected credential retrieval
    instructions.

Northflank templates can receive different arguments and secret overrides for
each run. Never commit generated `argument-overrides.json` or real merchant
credentials.

## Template preparation

```bash
python ../../scripts/prepare-deployment.py \
  --input /secure/path/deployment-input.json \
  --output-dir ../../.generated
```

Generated files:

```text
.generated/northflank/arguments.json
.generated/northflank/argument-overrides.json   # secret, mode 0600
```

The agent uses Northflank's API, CLI, or template-run interface to supply both
objects. The committed template has `autorun: false` so placeholder arguments
cannot accidentally create an insecure deployment.

## Domain prerequisite

Northflank requires the merchant domain to be added and verified for the team
before linking it to the edge port. An agent may automate this with Northflank
and a narrowly scoped DNS-provider API token, or present the one required DNS
record for manual creation.

## Customized UI

The default UI uses the public kit repository and:

```text
UI_DOCKER_WORK_DIR=/merchant-store-vibe-coding-kit/source/merchant-store
UI_DOCKERFILE_PATH=/merchant-store-vibe-coding-kit/source/merchant-store/Dockerfile
```

A customized UI repository must retain the runtime container contract:

- listen on port 80;
- answer `/healthz` with HTTP 200;
- accept `ESTORE_APP_PUBLIC_URL=/api` at startup;
- never contain merchant credentials or the Keycloak client secret.

## Release gate

The template is statically checked for ordering, private-service exposure,
secret placeholders, and the canonical environment-variable contract. A real
Northflank template import/run, domain verification, certificate issuance, and
public smoke test remain mandatory before general availability.
