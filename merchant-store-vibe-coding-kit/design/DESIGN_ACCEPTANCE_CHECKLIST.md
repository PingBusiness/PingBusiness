# Design acceptance checklist

## Complete deliverable

- [ ] A complete source tree is delivered, not screenshots or snippets.
- [ ] Every supplied production asset is used or explicitly rejected with a reason.
- [ ] Inspiration-only assets are not shipped.
- [ ] `DESIGN_REPORT.md` documents design tokens, assets, changed files, and validation.

## Build and deployment contract

- [ ] `npm ci` succeeds in a clean networked runner.
- [ ] `npm run build:prod` succeeds.
- [ ] Docker image builds and serves `/healthz`.
- [ ] `ESTORE_APP_PUBLIC_URL` configures the backend URL at container startup without rebuilding Angular.
- [ ] Direct refresh of every SPA route returns the application.

## Security

- [ ] Browser source/bundles/runtime config contain no Ping Business, Keycloak, database, or infrastructure secret.
- [ ] UI calls only `estore-app`.
- [ ] No server-to-server headers are created by the browser.
- [ ] Bearer and refresh tokens are not logged or sent to third parties.
- [ ] No unsafe merchant HTML or arbitrary SVG is injected.

## Functional behavior

- [ ] Public catalogue/product/inventory/media/download flows work.
- [ ] Registration, login, token refresh, logout, profile, and password-change flows work.
- [ ] Cart lines are re-read and inventory-revalidated before checkout.
- [ ] Recurring products are excluded from ordinary cart checkout.
- [ ] Ordinary checkout uses JSON launch data and form-posts the exact returned fields.
- [ ] Subscription checkout preserves its separate HTML/redirect protocol.
- [ ] `postMessage` is only a wake-up hint.
- [ ] Only authenticated checkout-status polling determines success/failure.
- [ ] Orders, order items, subscriptions, and payments remain read-only.

## User experience and accessibility

- [ ] Design works at 320, 375, 768, 1024, and 1440 pixels.
- [ ] Keyboard operation and focus visibility are complete.
- [ ] Labels, errors, loading states, and status changes are accessible.
- [ ] Colour contrast meets the agreed target.
- [ ] Reduced-motion preference is respected.
- [ ] Loading, empty, error, disabled, pending, success, timeout, and recovery states are designed.
