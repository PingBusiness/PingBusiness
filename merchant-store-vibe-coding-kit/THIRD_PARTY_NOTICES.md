# Third-party software notices

The Apache-2.0 license in this directory covers the original Ping Business
software, documentation, prompts, deployment templates, and scripts in this
kit. Third-party software is not relicensed by Ping Business and remains under
its respective upstream license.

The repository does not vendor `node_modules`, Python wheels, container-image
filesystems, PostgreSQL binaries, Keycloak binaries, Caddy binaries, or Apache
HTTP Server binaries. Package managers and container registries retrieve those
components during build or deployment.

## Direct frontend dependencies

The versions below are resolved by `source/merchant-store/package-lock.json`.

| Component | Resolved version | Upstream license |
| --- | ---: | --- |
| Angular packages (`@angular/*`) | 18.2.x | MIT |
| RxJS | 7.8.2 | Apache-2.0 |
| tslib | 2.8.1 | 0BSD |
| zone.js | 0.14.10 | MIT |
| TypeScript | 5.4.5 | Apache-2.0 |
| Node type declarations | 12.20.55 | MIT |

## Direct backend dependencies

The versions below are pinned by `source/estore-app/requirements.txt`.

| Component | Version | Upstream license |
| --- | ---: | --- |
| Flask | 3.1.3 | BSD-3-Clause |
| Flask-Cors | 6.0.2 | MIT |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| Requests | 2.34.2 | Apache-2.0 |
| Gunicorn | 26.0.0 | MIT |

## Validation tooling

| Component | Version | Upstream license |
| --- | ---: | --- |
| PyYAML | 6.0.2 | MIT |

## Referenced container images

| Image family | Purpose | Upstream licensing note |
| --- | --- | --- |
| `quay.io/keycloak/keycloak:26.7.0` | Identity service | Keycloak is Apache-2.0; image contents also include third-party components. |
| `postgres:16-alpine` | Keycloak database | PostgreSQL License plus Alpine packages under their respective licenses. |
| `caddy:2.11.4-alpine` | Public edge router | Caddy is Apache-2.0; Alpine packages retain their own licenses. |
| `httpd:2.4-alpine` | Merchant-store static server | Apache HTTP Server is Apache-2.0; Alpine packages retain their own licenses. |
| `node:22-alpine` | Angular build stage | Node.js and bundled components retain their upstream licenses. |
| `python:3.13-slim` | Python runtime/build stages | Python and distribution packages retain their upstream licenses. |

This file is a direct-dependency inventory, not a substitute for an SBOM or
for the license files embedded in downloaded packages and images. Before a
production release, generate and retain dependency/container SBOMs and preserve
all upstream notices required by the exact artifacts deployed.
