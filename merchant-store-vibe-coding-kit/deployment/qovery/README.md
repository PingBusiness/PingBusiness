# Qovery deployment adapter

This adapter creates the complete merchant-store environment in an existing
Qovery organization and deployed cluster. It deliberately exposes only one
service: the edge router on the merchant's single store hostname.

```text
https://shop.example.com/       -> private merchant-store UI
https://shop.example.com/api/*  -> private estore-app
https://shop.example.com/auth/* -> private Keycloak
```

PostgreSQL, Keycloak, `estore-app`, and the UI have private ports only. Qovery
terminates TLS for the edge custom domain.

Qovery clones `https://github.com/PingBusiness/PingBusiness` and receives `kit_repository_root_path = "/merchant-store-vibe-coding-kit"`.

## Nontechnical merchant flow

The merchant supplies the public vibe-kit URL, Ping Business credentials, one
hostname, a preferred region, and optionally a customized UI repository. An
authorized agent should then:

1. retrieve this repository;
2. discover or provision the merchant's Qovery organization and cluster;
3. gather the small input object defined by `../deployment-input.schema.json`;
4. run `../../scripts/prepare-deployment.py` without printing secrets;
5. export `QOVERY_API_TOKEN` from an authorized session;
6. run Terraform using the generated private tfvars;
7. configure the single DNS CNAME from `dns_validation_target`, automatically
   only when narrowly scoped DNS authorization exists;
8. wait for Qovery's managed certificate;
9. run the public smoke tests and return the URLs and protected credential
   retrieval instructions.

## Commands used by the agent

```bash
python ../../scripts/prepare-deployment.py \
  --input /secure/path/deployment-input.json \
  --output-dir ../../.generated

terraform init
terraform plan -var-file=../../.generated/qovery/terraform.tfvars.json
terraform apply -var-file=../../.generated/qovery/terraform.tfvars.json
terraform output
```

The Qovery token, generated tfvars, Terraform state, and merchant credentials
must remain outside Git. Production automation should use encrypted remote
state with access control and locking.

## Deployment order

Qovery deployment stages enforce:

1. private PostgreSQL;
2. private Keycloak;
3. lifecycle job that idempotently reconciles and verifies the ESTORE realm;
4. private `estore-app`;
5. private default or customized UI;
6. public edge, domain, and TLS.

## Customized UI

A customized UI repository must retain the runtime container contract:

- listen on port 80;
- answer `/healthz` with HTTP 200;
- accept `ESTORE_APP_PUBLIC_URL` at container startup;
- write that value into browser runtime configuration;
- never contain Ping Business credentials or Keycloak client secrets.

The default bundled UI uses `ESTORE_APP_PUBLIC_URL=/api`.

## Release gate

The HCL is pinned to Qovery provider `0.86.1` and is statically validated in
this kit. A real Qovery apply, DNS validation, certificate issuance, and public
smoke test remain mandatory before advertising the adapter as generally
available.
