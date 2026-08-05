# Static Ping Business store launcher

`pingbusiness-store-launcher.html` is a standalone, dependency-free prompt
generator for the public Ping Business website.

It supports two merchant workflows:

1. generate a design prompt, then attach brand assets to a trusted coding agent
   and download the customized UI source package;
2. generate a deployment prompt, then attach that customized UI package (or
   repository) and let an authorized agent deploy through Railway, Northflank, or
   the merchant's own server. Step 1 is not optional: the kit's own storefront is
   a reference implementation and is never deployed.

The page has no backend and does not submit form values anywhere. It deliberately
contains no merchant-API-key field. The deployment agent must request
`PINGBIZ_MERCHANT_API_KEY` only when it can write the value directly to the
selected hosting platform's protected secret system.

The authoritative repository, branch, kit-root, and raw `AGENTS.md` URLs are
fixed constants. Do not replace them with merchant-editable fields.

To publish it, copy the file into the Ping Business public website and apply the
site's normal headers, analytics policy, CSP, and branding wrapper. Test prompt
generation after any surrounding-site JavaScript or CSS is added.
