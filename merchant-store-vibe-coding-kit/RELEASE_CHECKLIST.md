# Public release checklist

## Completed for `1.0.0-rc3`

- [x] Apply Apache License 2.0 in `LICENSE`.
- [x] Add `NOTICE`, `TRADEMARKS.md`, and `THIRD_PARTY_NOTICES.md`.
- [x] Resolve the public repository URL as `https://github.com/PingBusiness/PingBusiness`.
- [x] Resolve the monorepo kit root as `/merchant-store-vibe-coding-kit`.
- [x] Update the static launcher to use `https://github.com/PingBusiness/PingBusiness/tree/main/merchant-store-vibe-coding-kit`.
- [x] Keep the merchant API key out of the static HTML and generated AI prompts.
- [x] Derive `BIZ_APP_BASE_URL` from staging/production selection.
- [x] Add Compose, Railway, and Northflank adapters.
- [x] Add a monorepo-aware GitHub Actions workflow.
- [x] Add machine-readable `kit-metadata.json`.
- [x] Include Apache-2.0 license and notice copies in standalone UI/backend source directories.
- [x] Run `./scripts/validate.sh` successfully.

## Live release gates still required

- [ ] Run the merchant UI clean production build in a networked CI runner.
- [ ] Build all Docker images.
- [ ] Run the full Compose stack against staging PingBusiness credentials.
- [ ] Complete customer registration, login, refresh, logout, catalogue,
      inventory, ordinary checkout, subscription, order, and payment-read tests.
- [ ] Restore a Keycloak PostgreSQL backup into a clean environment.
- [ ] Publish and test a Railway project/template.
- [ ] Complete one real self-hosted deployment on an authorized server, including
      certificate issuance and a tested backup.
- [ ] Complete one real Northflank deployment and capture its shared-template URL.
- [ ] Verify custom DNS and managed TLS on each advertised platform.
- [ ] Verify PostgreSQL, Keycloak, `estore-app`, and the raw UI are not public.
- [ ] Verify no secrets occur in browser bundles, runtime config, source maps,
      reports, or Git history.
- [ ] Publish website platform buttons only for adapters that passed live tests.
- [ ] Replace the release-candidate tag with stable `merchant-store-vibe-kit-v1.0.0`.
- [ ] Publish a non-prerelease asset named `pingbusiness-merchant-store-vibe-coding-kit.zip`.
