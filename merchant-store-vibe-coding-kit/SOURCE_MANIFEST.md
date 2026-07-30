# Canonical source manifest

This release candidate was constructed from the following user-supplied canonical artifacts on **2026-07-30**.

| Artifact | Canonical role | SHA-256 |
|---|---|---|
| `merchant-store-master(1).zip` | Canonical Ping Business merchant-store UI; supersedes every prior `estore-ui` package. | `a2b7d90232ab420e11f71c67761bd432d6d0f06e40e0f94a6d99e1e57a02c0da` |
| `pingbiz-master(26).zip` | Canonical Ping Business source package; current `estore-app` is `/app/estore/app.py` with its Dockerfile and requirements in the same directory. | `8543ba44f4abbe776961c3b0fafda0fe4f051beabccbbf80d941801b8a3140aa` |
| `ESTORE-realm-template.json` | Sanitized portable ESTORE realm reference. | `7ea8632c8f2d7dc360ef99ad1ee3a8a21c607e3cb6ac04cf7fdf3c2ddf9dd3b1` |
| `pingbusiness-estore-vibe-coding-kit(2).zip` | Previous vibe-kit package, used for reference only and rebuilt here. | `c21941ba539faaa81f19620614d2378ccd02597e5fc2147278139125109fbff1` |

## Explicit exclusion

The `/estore-ui` directory inside `pingbiz-master(26).zip` is obsolete and was intentionally not used. Only `merchant-store-master(1).zip` is authoritative for the UI.

## Integrity rule

The bundled `source/estore-app/app.py` and `requirements.txt` are byte-identical to their canonical files in `pingbiz-master(26).zip`. Pipeline changes are isolated to container/deployment support and the separately supplied UI.
