# Merchant asset manifest

List every file supplied to the design agent. File names must match exactly. Never put secrets, production customer data, or private keys in this manifest.

| File | Type | Intended use | Production or inspiration-only | Crop/placement | Background | Required alt text | Rights/expiry | Allowed transformations |
|---|---|---|---|---|---|---|---|---|
| `example-logo.svg` | Logo | Header/footer | Production | Preserve mark and clear space | Light/dark | Merchant name | Merchant-owned | Resize only |
|  |  |  |  |  |  |  |  |  |

## Theme files

| File | Information | Authority | Notes |
|---|---|---|---|
|  | Palette / typography / spacing / reference | Required / preferred / inspiration |  |

## Fonts

| Family/file | Weights/styles | Web embedding licensed? | Fallback | Notes |
|---|---|---|---|---|
|  |  |  |  |  |

Do not invent font rights. When web embedding permission is unclear, use a safe system fallback.

## Content files

| File | Destination | May copy be edited? | Locale | Notes |
|---|---|---:|---|---|
|  |  |  |  |  |

## Image handling rules

- focal points/crop priority:
- prohibited crops:
- transparency handling:
- responsive formats allowed:
- metadata removal required:
- decorative versus informative rules:

## SVG safety

Trusted production SVGs should be served as vetted static assets. Do not inject arbitrary SVG markup using `innerHTML`. Remove scripts, event handlers, external references, and unsafe embedded content.
