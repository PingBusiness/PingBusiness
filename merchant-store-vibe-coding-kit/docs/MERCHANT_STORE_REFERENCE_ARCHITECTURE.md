# Canonical merchant-store UI reference

**Source:** `merchant-store-master(1).zip`, with deployment-only changes in `SOURCE_PATCHES.md`  
**Framework:** Angular 18.2, RxJS 7.8, TypeScript 5.4  
**Package:** `pingbiz-estore-customer-ui`  
**Version:** `1.1.0`

## Routes and responsibilities

The application includes home, catalogue, product, cart, checkout, recurring
subscription, orders, subscriptions, account, sign-in, and sign-up flows.
Orders, order items, subscriptions, and payments remain read-only.

## Runtime configuration

`src/index.html` loads `/assets/runtime-config.js` before Angular. The production
container writes:

```javascript
window.__PINGBUSINESS_CONFIG__ = Object.freeze({
  apiUrl: "/api"
});
```

`app.configs.ts` reads this value. A deliberate separate-origin deployment may
supply a full HTTPS URL, but the default pipeline uses same-origin `/api`.

## Authentication

The UI does not expose Keycloak directly. It calls `estore-app` login, refresh,
logout, and user endpoints. Session state stays in `sessionStorage`; refresh
failure clears the session. Agents must not create competing refresh mechanisms
or attach tokens to third-party payment URLs.

## Catalogue, inventory, and cart

Only approved products are displayed. Media is loaded through `estore-app` and
object URLs are revoked. Cached cart values are presentation hints; product and
inventory state are re-read before checkout. Recurring products use the
subscription flow rather than ordinary cart checkout.

## Ordinary checkout

The UI requests JSON from `POST /checkout`, stores the checkout ID, form-posts
the exact returned payment fields in a controlled popup, and polls authenticated
`/checkout/status/{id}`. Browser messages are not authoritative.

## Subscription checkout

`POST /subscribe` is a separate single-product recurring flow. The UI launches
the controlled redirect/popup/iframe fallback and polls the same authoritative
status endpoint without conflating the ordinary and recurring response formats.

## Customization boundaries

Safe: styles, design tokens, layout, copy, assets, accessibility, component
composition, and responsive behavior.

Contract review required: routes, API payloads, token lifecycle, cart
revalidation, checkout launch/status semantics, and runtime configuration.
