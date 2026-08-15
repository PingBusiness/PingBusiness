# PingBusiness eStore API specification

**Specification date:** 2026-08-14  
**Audience:** storefront UI developers, merchant eStore operators, integration teams, QA, security, operations, and AI code-generation teams

## 1. Purpose and scope

`estore-app` is the customer-facing storefront API and checkout gateway for one configured PingBusiness merchant/store deployment. It mediates between customer applications, the ESTORE Keycloak realm, the central `biz-app`, and PaymentAsia checkout workflows.

Each running `estore-app` instance is bound at startup to exactly one configured merchant and one configured store. Public catalog calls are automatically limited to that store, while customer order/payment calls are additionally limited to the authenticated customer identity.

The service is responsible for:

- customer registration and ESTORE Keycloak account creation;
- customer password-grant login, refresh, logout, token introspection, profile reads, profile edits, and password changes;
- public reads of the configured store, approved products, product files/media, and product inventory;
- customer-scoped reads of orders, order items, and one-time payments;
- customer-initiated cancellation of the authenticated customer's recurring subscription order items;
- one-time PaymentAsia Standard hosted checkout initiation;
- recurring/subscription PaymentAsia tokenization initiation;
- forwarding PaymentAsia return/notify payloads to `biz-app` for authoritative verification/finalization;
- browser-safe checkout return pages and authenticated checkout-status polling;
- enforcing merchant/store/customer scope before forwarding business-data calls.

`estore-app` does **not** directly own PingBusiness business records. `biz-app` remains authoritative for merchants, stores, products, inventory, customers, intents, orders, order items, payments, recurring schedules, and recurring payment execution records.

```text
Customer browser / storefront UI
        |
        | ESTORE bearer token for customer-scoped APIs
        | public access for catalog/media
        v
+---------------------------+
|         estore-app        |
| one merchant + one store  |
+---------------------------+
     |                 |
     |                 | ESTORE realm auth/admin
     |                 v
     |             Keycloak
     |
     | merchant API key + merchant/store identifiers
     v
+---------------------------+
|          biz-app          |
+---------------------------+
     |
     | selects/persists PaymentAsia test/live environment
     v
 PaymentAsia helper service(s)
     |
     v
 PaymentAsia gateway

PaymentAsia return/notify
        |
        v
     estore-app callback routes
        |
        v
     biz-app verification/finalization
```

### 1.1 Trust boundary

The browser is not trusted to choose authoritative prices, inventory, merchant/store ownership, payment success, subscription terms, or provider result state.

The following values are server-only secrets and must not be embedded in storefront JavaScript, public mobile bundles, HTML, source maps, or browser storage:

- `ESTORE_CLIENT_SECRET`;
- `PINGBIZ_MERCHANT_API_KEY`;
- Keycloak administrative/service-account tokens obtained with the client secret;
- internal `BIZ_APP_BASE_URL` connectivity details when those expose private infrastructure.

The configured merchant/store identifiers are public scope identifiers rather than secrets, but they do not authorize `biz-app` by themselves. Server-to-server calls also require the merchant API key.

Customer bearer and refresh tokens are customer credentials. They are accepted only by the appropriate customer authentication flows and do not grant merchant-manager or platform-administrator privileges.

`estore-app` never trusts a callback merely because it reached a public callback URL. Callback payloads are forwarded to `biz-app`, which owns PaymentAsia signature verification and authoritative payment/subscription finalization.

## 2. Base URL and transport

Examples in this specification use:

```text
https://store-api.example.com
```

Production deployments should use HTTPS.

JSON requests normally use:

```http
Content-Type: application/json
Accept: application/json
```

Customer-scoped calls send:

```http
Authorization: Bearer <ESTORE access token>
```

Important non-JSON responses:

- `GET /image/{file_id}` relays inline image bytes from `biz-app`;
- `GET /download?file_id={id}` relays attachment bytes;
- successful `POST /checkout` returns HTML by default, or JSON when `response_mode = "json"`;
- successful `POST /subscribe` returns HTML that redirects the browser to PaymentAsia tokenization;
- browser return routes return HTML status pages;
- PaymentAsia notify routes return JSON.

When run directly, the service listens on `0.0.0.0` and `ESTORE_APP_PORT`, default `5000`.

HTML checkout/return responses are emitted with:

```http
Cache-Control: no-store
```

If configured, the service also emits a checkout-page `Content-Security-Policy` `frame-ancestors` directive.

## 3. Deployment configuration that affects the API

### 3.1 Required environment variables

| Variable | Purpose |
|---|---|
| `PINGBIZ_MERCHANT_IDENTIFIER` | Public merchant identifier for the merchant owned by this eStore deployment. Startup fails when absent. |
| `PINGBIZ_STORE_IDENTIFIER` | Public store identifier for the single store owned by this eStore deployment. Startup fails when absent. |
| `PINGBIZ_MERCHANT_API_KEY` | Raw merchant API key used only server-side for scoped `biz-app` calls. Startup fails when absent. |
| `ESTORE_CLIENT_SECRET` | Confidential Keycloak client secret for the ESTORE realm. Used for customer token introspection and Keycloak administrative operations. Startup fails when absent. |

### 3.2 Optional environment variables

| Variable | Default | Effect |
|---|---:|---|
| `ESTORE_APP_PORT` | `5000` | Flask listen port when run directly. |
| `DEV_MODE` | `true` | When true, CORS is open. When false, allowed origins come from `ESTORE_ALLOWED_ORIGINS`. |
| `BIZ_APP_BASE_URL` | `http://biz-app:5000` | Internal central PingBusiness API URL. |
| `ESTORE_REALM` | `ESTORE` | Customer Keycloak realm. |
| `ESTORE_CLIENT_ID` | `estore-app` | Confidential ESTORE client used for password grants, refresh, introspection, client credentials, and account administration. |
| `ESTORE_KC_SERVER_URL` | `KC_SERVER_URL` or `http://k-keycloak:8080/auth/` | Keycloak base URL. Trailing slash is normalized away. |
| `KC_SERVER_URL` | `http://k-keycloak:8080/auth/` | Fallback Keycloak base URL when `ESTORE_KC_SERVER_URL` is absent. |
| `ESTORE_CUSTOMER_ROLE` | empty | Optional ESTORE realm role assigned to newly created Keycloak customer accounts. |
| `ESTORE_PUBLIC_BASE_URL` | empty | Explicit public origin used to construct PaymentAsia return/notify URLs. |
| `ESTORE_CHECKOUT_LANG` | empty | Default PaymentAsia checkout language forwarded for standard checkout when the request does not provide `lang`. |
| `ESTORE_CHECKOUT_FRAME_ANCESTORS` | empty | Optional CSP `frame-ancestors` value added to generated checkout/return HTML. |
| `ESTORE_TRUST_PROXY_HEADERS` | `true` | Enables `ProxyFix` handling of one forwarded hop for client IP, scheme, host, and port. |
| `ESTORE_ALLOWED_ORIGINS` | empty | Comma-separated CORS origins used only when `DEV_MODE=false`. |

The token/logout/admin URLs are derived from the Keycloak server, realm, and client configuration.

### 3.3 Startup merchant/store resolution

Startup is not lazy. After configuration is loaded, `estore-app` immediately resolves its configured merchant and store through scoped `biz-app` requests:

1. `GET /merchants?identifier=<PINGBIZ_MERCHANT_IDENTIFIER>`;
2. `GET /stores?identifier=<PINGBIZ_STORE_IDENTIFIER>`;
3. each lookup must return exactly one object;
4. the resolved store's `merchant_id` must equal the resolved merchant's `id`.

The resulting integer merchant/store IDs are retained in-process as the canonical eStore scope. Startup fails if the configured identifiers cannot be resolved or do not belong together.

Because `biz-app` scoped eStore authentication requires an active merchant, a suspended merchant cannot be resolved into a functioning eStore deployment through these requests.

### 3.4 Server-to-server `biz-app` authentication

Every ordinary eStore-to-business request carries:

```http
X-PingBiz-API-Key: <PINGBIZ_MERCHANT_API_KEY>
X-PingBiz-Merchant-Identifier: <PINGBIZ_MERCHANT_IDENTIFIER>
X-PingBiz-Store-Identifier: <PINGBIZ_STORE_IDENTIFIER>
Content-Type: application/json
```

Binary relays omit `Content-Type` on the outgoing `GET` but use the same three scope/authentication headers.

The browser never receives the merchant API key.

### 3.5 PaymentAsia environment routing

`estore-app` does not connect directly to a PaymentAsia helper and does not choose a test/live provider URL itself. Standard and recurring PaymentAsia operations are submitted to `biz-app`:

- `POST /pa/checkout` for standard checkout launch;
- `POST /paymentasia/record_payment` for standard payment recording;
- `POST /recurring/checkout` for recurring tokenization/schedule initiation;
- `POST /recurring/tokenization/record` for recurring tokenization completion;
- `POST /recurring/payment/record` for recurring execution callbacks.

The selected PaymentAsia environment is therefore a `biz-app` concern, based on the configured store and persisted payment workflow state. eStore clients do not send a provider-mode selector.

## 4. Authentication and actor model

### 4.1 Public storefront routes

The following routes do not require a customer bearer token:

- `GET /health`
- `POST /login`
- `POST /logout`
- `POST /refresh`
- `POST /customer` **when creating a customer** (body has no `id`)
- `GET /payment_networks`
- `GET /store`
- `GET /store/{store_id}`
- `GET /products`
- `GET /product/{product_id}`
- `GET /inventories`
- `GET /file/{file_id}`
- `GET /image/{file_id}`
- `GET /download`
- `GET|POST /checkout/return/{checkout_id}`
- `POST /checkout/notify/{checkout_id}`
- `GET|POST /recurring/tokenization/return/{checkout_id}`
- `POST /recurring/tokenization/notify/{checkout_id}`
- `POST /recurring/payment/notify`

"Public" does not mean unscoped. Catalog and media routes are still constrained to the single configured store and approved products. Callback routes are provider-facing and are not trusted as successful until downstream verification completes.

### 4.2 Customer bearer-token authentication

Customer-protected routes require an access token issued by the configured ESTORE realm/client:

```http
Authorization: Bearer <ESTORE access token>
```

`estore-app` introspects the token with the confidential client and accepts it only when:

- the introspection response contains literal JSON boolean `active: true`;
- the response includes a non-empty `sub` claim.

False, missing, null, or merely truthy non-boolean `active` values are rejected.

The Keycloak subject (`sub`) is the authoritative customer identity mapping used with `biz-app`. The corresponding `BCustomers.username` value is the Keycloak subject, not the customer's email address.

Protected customer routes include:

- `GET /user`
- `POST /customer` **when updating an existing customer**
- `GET /customer`
- `POST /customer/update_password`
- `GET /orders`
- `GET /order/{order_id}`
- `GET /order_items`
- `GET /order_item/{order_item_id}`
- `POST /order_item/{order_item_id}/recurring/cancel`
- `GET /payments`
- `GET /payment/{payment_id}`
- `POST /checkout`
- `POST /subscribe`
- `GET /checkout/status/{checkout_id}`

### 4.3 Customer lookup and store scope

For an authenticated customer, `estore-app` resolves the current business profile through:

```text
GET biz-app /customers
    ?merchant_id=<configured merchant id>
    &store_id=<configured store id>
    &username=<customer token sub>
```

If no matching profile exists, customer-scoped business routes return:

```json
{
  "error": "Customer profile not found for this estore"
}
```

with HTTP `404`.

This makes customer identity store-specific: the same external person is not treated as the same business customer across stores merely because an email address matches.

### 4.4 Customer registration identity model

Customer registration creates two linked records:

1. an ESTORE Keycloak user;
2. a `biz-app` customer row whose `username` stores that Keycloak user's ID/subject.

The signup request's human login `username` and `email` are Keycloak-facing attributes; they are **not** copied into the business customer's `username` field.

When business-customer creation fails after Keycloak user creation, `estore-app` attempts to delete the newly created Keycloak account as compensating rollback.

### 4.5 Provider callback authentication model

PaymentAsia callback routes do not require a customer token because provider servers and browser navigation cannot supply one reliably. They instead rely on the downstream payment workflow:

- standard payment payloads are sent to `biz-app /paymentasia/record_payment`;
- recurring tokenization payloads are sent to `biz-app /recurring/tokenization/record`;
- recurring execution payloads are sent to `biz-app /recurring/payment/record`.

`biz-app` and the selected internal PaymentAsia helper perform authoritative signature/result verification and bind the result to trusted intent/schedule state.

A public callback route must therefore never be interpreted by a caller as an unauthenticated API for setting success state.

## 5. General response and error conventions

### 5.1 JSON errors

Locally generated errors normally use:

```json
{
  "error": "Human-readable message"
}
```

Many business-resource responses and errors are directly relayed from `biz-app`, preserving its HTTP status code and JSON body.

A client should tolerate at least `400`, `401`, `403`, `404`, `409`, `500`, and `502` on applicable routes.

### 5.2 Upstream response relay

For most JSON proxy operations:

- if `biz-app` returns `204`, eStore returns an empty `204`;
- otherwise the upstream JSON body and status are relayed;
- if an internal HTTP response is not JSON, the internal request helper represents it as `{ "raw": "..." }` for JSON proxy purposes.

Several singular eStore routes convert upstream `204` not-found responses to local `404` before returning them, because eStore scope validators need a concrete missing-resource result.

### 5.3 Binary relay

`GET /image/{file_id}` and `GET /download` fetch bytes from `biz-app` and relay the response while removing hop-by-hop headers such as `connection`, `content-length`, `transfer-encoding`, and related transport headers.

The business API remains authoritative for stored MIME type, filename, disposition, and byte content.

### 5.4 HTML checkout responses

Generated checkout and return pages are HTML, not JSON. They always include `Cache-Control: no-store`.

The return page attempts to notify a parent frame and `window.opener` with a browser message of this shape:

```json
{
  "type": "PINGBIZ_ESTORE_CHECKOUT_COMPLETE",
  "success": true,
  "statusLabel": "successful",
  "orderId": 123,
  "order_id": 123,
  "paymentReference": "provider-reference",
  "payment_reference": "provider-reference",
  "checkoutId": "intent-identifier",
  "checkout_id": "intent-identifier"
}
```

The same page may report processing, failed, uncertain, unavailable, or successful state. Storefront code should use authenticated `GET /checkout/status/{checkout_id}` as the durable fallback rather than trusting browser message delivery alone.

### 5.5 Monetary values

Money originates from `biz-app` as fixed-point strings such as:

```json
"29.90"
```

For checkout, `estore-app` parses amounts with decimal arithmetic. Current product unit price must be greater than zero. Line amount is calculated as:

```text
current product amount * requested quantity
```

and quantized to two decimal places.

The browser does not supply authoritative unit prices or totals.

### 5.6 IDs and checkout identifiers

- Business `id` fields are integer primary keys.
- Resource `identifier` fields are public strings generated by `biz-app` or supplied under its resource-specific rules.
- Checkout IDs returned by eStore are `BIntents.identifier` values.
- Standard/subscription `merchant_reference` values are generated as UUID4 strings before intent creation and become the immutable intent reference.

### 5.7 Date/time and recurring start dates

Business timestamps are relayed in the JSON representation produced by Flask/`biz-app`.

For subscription checkout, `estore-app` derives `recurring_start_date` as the **next calendar date in `Asia/Hong_Kong`** at checkout construction time. The recurring start date is not accepted from the browser.

### 5.8 Query-field scope override

On customer collection routes, eStore copies query parameters and then overwrites customer/merchant/store filters with trusted values. Caller-controlled values cannot broaden scope.

On catalog routes, eStore forces the configured store and approved product state even when the caller supplies different filters.

## 6. Controlled values and workflow state

### 6.1 Product storefront visibility

Only product state:

```text
A = Approved/published
```

is visible through eStore catalog, product, file, media, inventory, and checkout workflows.

Requests that explicitly ask `/products` for `D`, `S`, or `R` are rejected with `403`. Direct product/file/media reads also validate that the parent product is currently approved.

`review_notes` are not exposed to eStore actors by `biz-app` and therefore do not appear in storefront product payloads.

### 6.2 PaymentAsia Standard payment networks

Supported network names are case-sensitive and exactly:

- `Alipay`
- `Wechat`
- `CUP`
- `CreditCard`
- `Fps`
- `Octopus`
- `PayMe`

`GET /payment_networks` returns the subset currently enabled on the configured merchant.

`POST /checkout` requires one selected network, and it must be in that current merchant list. The browser cannot request `UserDefine` or any unsupported/unconfigured network.

Subscription tokenization requires `CreditCard` to be enabled and does not accept another network choice.

### 6.3 Ordinary versus subscription products

A product is treated as ordinary when all three recurring fields are null/empty:

- `recurring_frequency`
- `recurring_intervals`
- `recurring_total_execution_times`

A product is treated as a subscription product only when all three are present and valid.

Supported frequencies recognized by eStore are:

- `WEEKLY`
- `MONTHLY`
- `YEARLY`

`recurring_intervals` and `recurring_total_execution_times` must be positive integers.

Standard cart checkout rejects subscription products. `POST /subscribe` rejects ordinary products. Subscription checkout supports exactly one product ID plus quantity.

### 6.4 Intent status

Checkout intents are created with status `C`.

The current trusted intent status set used by the PingBusiness checkout workflow is:

| Code | Storefront meaning |
|---|---|
| `C` | Created; checkout has not yet reached a terminal result. |
| `R` | Redirected/processing; explicitly non-terminal for storefront polling. |
| `S` | Successful; terminal. |
| `F` | Failed; terminal. |
| `U` | Uncertain/reconciliation required; terminal for the immediate browser polling cycle but not a successful purchase. |

`GET /checkout/status/{checkout_id}` reports `complete=true` only for `S`, `F`, or `U`.

### 6.5 Order-item delivery state

Customer order-item reads include:

| Value | Meaning |
|---|---|
| `null` | Not marked delivered. |
| `D` | Delivered. |

If an upstream order-item payload omits the field, eStore inserts `state: null` so storefront clients receive a stable shape.

There is no customer-facing eStore route to change delivery state.

### 6.6 Recurring order-item fields

A successfully created subscription order item may contain:

- `recurring_start_date`;
- `recurring_frequency`;
- `recurring_intervals`;
- `recurring_total_execution_times`;
- `recurring_merchant_reference`;
- `recurring_status`;
- sanitized `subscription_details`.

Sensitive tokenization/provider-token/signature keys are removed by the authoritative `biz-app` serializer before eStore receives the order item.

`estore-app` exposes recurring state through ordinary order/order-item reads and checkout status, and allows an authenticated customer to cancel a recurring order item that belongs to that customer through `POST /order_item/{order_item_id}/recurring/cancel`. It does not expose customer routes for recurring adjustment or manual reconciliation.

## 7. Resource schemas

Fields may be `null` where indicated by the underlying business record.

### 7.1 `AuthTokenResponse`

`POST /login` and successful `POST /refresh` return the ESTORE Keycloak token JSON. Common fields include:

| Field | Type | Notes |
|---|---|---|
| `access_token` | string | Bearer token for customer-scoped eStore APIs. |
| `refresh_token` | string, optional | Used by `/refresh` and `/logout`. |
| `expires_in` | integer, optional | Access-token lifetime. |
| `refresh_expires_in` | integer, optional | Refresh-token lifetime. |
| `token_type` | string, optional | Normally `Bearer`. |
| `scope` | string, optional | Keycloak policy dependent. |
| other fields | any | Keycloak may return session/policy fields. |

### 7.2 `CurrentUser`

Returned by `GET /user`:

```json
{
  "sub": "keycloak-subject",
  "username": "customer@example.com",
  "email": "customer@example.com",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "customer_id": 42,
  "customer": { "...": "Customer" }
}
```

| Field | Type | Notes |
|---|---|---|
| `sub` | string | Authoritative ESTORE Keycloak subject. |
| `username` | string | Preferred username/username/email claim fallback, then subject. |
| `email` | string/null | Token email, falling back to business customer email. |
| `first_name` | string | Business profile value. |
| `last_name` | string | Business profile value. |
| `customer_id` | integer | Current store-local business customer ID. |
| `customer` | `Customer` | Complete business profile. |

### 7.3 `Customer`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Business customer ID. |
| `identifier` | string | Server-generated public identifier. |
| `merchant_id` | integer | Configured eStore merchant. |
| `store_id` | integer | Configured eStore store. |
| `first_name` | string | Required. |
| `last_name` | string | Required. |
| `details` | string/null | Free-form profile data. |
| `shipping_address` | string/null | Shipping address. |
| `billing_address` | string/null | Billing address; required during eStore signup. |
| `email` | string/null | Normalized validated signup/profile email. |
| `phone` | string/null | Phone; required during eStore signup. |
| `username` | string/null | ESTORE Keycloak subject mapping, not human login name. |
| `updated_at` | date/time/null | Audit value. |
| `created_at` | date/time | Audit value. |

### 7.4 `Store`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Configured store ID. |
| `identifier` | string | Public store identifier. |
| `merchant_id` | integer | Configured merchant ID. |
| `name` | string | Store name. |
| `details` | string/null | Store details. |
| `mode` | string | `T` or `L`; used downstream by PingBusiness payment routing. |
| `updated_at` | date/time/null | Audit value. |
| `created_at` | date/time | Audit value. |

### 7.5 `Product`

Storefront product reads include the business product fields plus an eStore-added `files` array.

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Product ID. |
| `identifier` | string/null | Product public identifier/SKU-like value. |
| `store_id` | integer | Always the configured eStore store. |
| `name` | string | Product name. |
| `details` | string/null | Free-form details. |
| `description` | string/null | Product description. |
| `amount` | decimal string | Current unit amount. |
| `currency` | string | Three-letter currency from business data. |
| `recurring_frequency` | string/null | `WEEKLY`, `MONTHLY`, `YEARLY`, or null for ordinary products. |
| `recurring_intervals` | integer/null | Interval multiplier for recurring products. |
| `recurring_total_execution_times` | integer/null | Finite scheduled execution count. |
| `state` | string | Always `A` through valid eStore product reads. |
| `updated_at` | date/time/null | Audit value. |
| `created_at` | date/time | Audit value. |
| `files` | `ProductFile[]` | Added by eStore for `/products` and `/product/{id}`. |

`review_notes` are intentionally absent from eStore product responses.

### 7.6 `ProductFile`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | File metadata ID. |
| `merchant_id` | integer | Owning merchant. |
| `product_id` | integer | Approved parent product. |
| `name` | string | Download filename. |
| `description` | string/null | File metadata. |
| `location` | string | Server-side storage-relative value; do not construct a public URL from it. |
| `size` | integer | Byte size. |
| `mime_type` | string/null | Stored MIME type. |
| `created_at` | date/time | Audit value. |

Use `/image/{file_id}` or `/download?file_id={file_id}` to obtain bytes.

### 7.7 `Inventory`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Inventory-row ID. |
| `product_id` | integer | Approved product. |
| `quantity` | integer | Quantity for one location row. |
| `location` | string | Inventory location. |
| `updated_at` | date/time/null | Audit value. |

`GET /inventories` returns all rows for one product. Storefront availability is the sum of the returned `quantity` values. An empty list means availability `0`.

### 7.8 `Order`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Order ID. |
| `identifier` | string | Server-generated public identifier. |
| `merchant_id` | integer | Configured merchant. |
| `customer_id` | integer | Authenticated customer's business ID. |
| `store_id` | integer | Configured store. |
| `status` | string | Business order status. `S` is successful in checkout workflows. |
| `currency` | string | Three-letter currency. |
| `subtotal_amount` | decimal string | Subtotal. |
| `total_amount` | decimal string | Total. |
| `details` | string/null | Business/provider workflow details. |
| `updated_at` | date/time/null | Audit value. |
| `created_at` | date/time | Audit value. |

### 7.9 `OrderItem`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Order-item ID. |
| `order_id` | integer | Parent customer order. |
| `order_status` | string/null | Current parent order status. |
| `product_id` | integer | Purchased product. |
| `quantity` | integer | Purchased quantity. |
| `unit_amount` | decimal string | Immutable checkout unit amount. |
| `amount` | decimal string | Purchased line amount. |
| `recurring_start_date` | date/null | Subscription start date. |
| `recurring_frequency` | string/null | Subscription frequency. |
| `recurring_intervals` | integer/null | Subscription interval multiplier. |
| `recurring_total_execution_times` | integer/null | Finite execution count. |
| `recurring_merchant_reference` | string/null | Active recurring-schedule reference when applicable. |
| `recurring_status` | string/null | Recurring schedule lifecycle status when applicable. |
| `subscription_details` | object/null | Sanitized subscription metadata. Provider token/signature secrets are removed. |
| `state` | string/null | Delivery state; `D` means delivered. |
| `details` | string/null | Business details. |
| `updated_at` | date/time/null | Audit value. |
| `created_at` | date/time | Audit value. |

### 7.10 `Payment`

One-time payment records are returned through `/payments` and `/payment/{id}`.

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Payment ID. |
| `identifier` | string | Public payment identifier. |
| `order_id` | integer | Parent customer order. |
| `merchant_id` | integer | Configured merchant. |
| `store_id` | integer | Configured store. |
| `currency` | string | Payment currency. |
| `amount` | decimal string | Payment amount. |
| `status` | string | Business/provider result status. Successful PaymentAsia finalization uses `S`. |
| `reference` | string/null | Provider payment/request reference. |
| `details` | string/null | Provider metadata stored by business workflow. |
| `created_at` | date/time | Audit value. |

Subscription schedule acceptance does not create a one-time `Payment` row merely for tokenization/schedule creation.

### 7.11 `PaymentNetworkConfiguration`

Returned by `GET /payment_networks`:

```json
{
  "payment_gateway": "PAYMENT_ASIA",
  "payment_networks": ["CreditCard", "Fps", "PayMe"]
}
```

### 7.12 `CheckoutLaunch`

Returned by `POST /checkout` when `response_mode = "json"`:

```json
{
  "checkout_id": "intent-identifier",
  "checkout_reference": "merchant-reference",
  "action_url": "https://payment-gateway.example/hosted-payment",
  "fields": {
    "merchant_reference": "merchant-reference",
    "currency": "HKD",
    "amount": "50.00",
    "sign": "..."
  }
}
```

`fields` is provider-driven and may contain additional PaymentAsia hosted-form fields. A popup client should create a real HTML form targeting `action_url` and submit the returned fields; it must not change authoritative values.

### 7.13 `CheckoutStatus`

Returned by authenticated `GET /checkout/status/{checkout_id}`:

```json
{
  "checkout_id": "intent-identifier",
  "complete": true,
  "success": true,
  "status": "S",
  "order_id": 123,
  "payment_reference": "provider-request-reference",
  "checkout_reference": "merchant-reference",
  "paymentasia_status": "1",
  "recurring_checkout_status": null
}
```

For subscription checkout, `recurring_checkout_status` may contain trusted recurring workflow state such as schedule-creation processing state.


## 8. Endpoint summary

| Method | Path | Authentication | Purpose / response |
|---|---|---|---|
| `GET` | `/health` | Public | Process liveness JSON. |
| `POST` | `/login` | Public | ESTORE password-grant token response. |
| `POST` | `/logout` | Public; refresh token in body | Revokes/logs out refresh session. |
| `POST` | `/refresh` | Public; refresh token in body | Refreshes ESTORE tokens. |
| `GET` | `/user` | Customer bearer | Current customer identity/profile summary. |
| `POST` | `/customer` | Public for create; bearer for update | Create customer login/profile or update own profile. |
| `GET` | `/customer` | Customer bearer | Current customer's `Customer`. |
| `POST` | `/customer/update_password` | Customer bearer | Change own ESTORE password after current-password verification. |
| `GET` | `/payment_networks` | Public | Current merchant PaymentAsia network allow-list. |
| `GET` | `/store` | Public | Configured `Store`. |
| `GET` | `/store/{store_id}` | Public | Store read, but only configured store ID is allowed. |
| `GET` | `/products` | Public | Approved configured-store `Product[]`, each with `files`. |
| `GET` | `/product/{product_id}` | Public | One approved configured-store `Product` with `files`. |
| `GET` | `/inventories` | Public | Inventory rows for one approved product. |
| `GET` | `/file/{file_id}` | Public | Metadata for a file of an approved configured-store product. |
| `GET` | `/image/{file_id}` | Public | Inline image bytes. |
| `GET` | `/download` | Public | Attachment bytes. |
| `GET` | `/orders` | Customer bearer | Current customer's scoped `Order[]`. |
| `GET` | `/order/{order_id}` | Customer bearer | One current-customer `Order`. |
| `GET` | `/order_items` | Customer bearer | Current customer's scoped `OrderItem[]`. |
| `GET` | `/order_item/{order_item_id}` | Customer bearer | One current-customer `OrderItem`. |
| `POST` | `/order_item/{order_item_id}/recurring/cancel` | Customer bearer | Cancel one recurring order item owned by the current customer. |
| `GET` | `/payments` | Customer bearer | Current customer's scoped one-time `Payment[]`. |
| `GET` | `/payment/{payment_id}` | Customer bearer | One current-customer `Payment`. |
| `POST` | `/checkout` | Customer bearer | Start standard hosted checkout for ordinary products. |
| `POST` | `/subscribe` | Customer bearer | Start PaymentAsia tokenization for one subscription product. |
| `GET` | `/checkout/status/{checkout_id}` | Customer bearer | Durable customer-scoped standard/subscription checkout state. |
| `GET`, `POST` | `/checkout/return/{checkout_id}` | Public gateway/browser return | Browser-safe standard checkout return page. |
| `POST` | `/checkout/notify/{checkout_id}` | Public gateway callback | Strict standard payment finalization forwarding. |
| `GET`, `POST` | `/recurring/tokenization/return/{checkout_id}` | Public gateway/browser return | Subscription tokenization browser return / signed result. |
| `POST` | `/recurring/tokenization/notify/{checkout_id}` | Public gateway callback | Strict subscription tokenization/schedule result forwarding. |
| `POST` | `/recurring/payment/notify` | Public gateway callback | Strict recurring execution result forwarding. |

## 9. Endpoint reference

### 9.1 Health and authentication

#### `GET /health`

Process-liveness endpoint. It does not authenticate a customer and does not perform explicit dependency health checks against `biz-app`, Keycloak, or PaymentAsia.

**Success - `200`**

```json
{
  "status": "ok",
  "service": "estore-app"
}
```

---

#### `POST /login`

Convenience ESTORE Keycloak Resource Owner Password Credentials login. Browser applications may instead use an appropriate direct Keycloak browser flow and then send the resulting ESTORE access token to protected eStore routes.

**Body**

```json
{
  "username": "customer@example.com",
  "password": "customer-password"
}
```

Both fields are required.

The request is forwarded to the configured ESTORE token endpoint with:

- `grant_type=password`;
- configured `ESTORE_CLIENT_ID`;
- confidential `ESTORE_CLIENT_SECRET`;
- supplied username and password.

**Success - normally `200`**: Keycloak token JSON.

**Errors**

- `400` missing username or password;
- otherwise the Keycloak token endpoint's HTTP status and JSON body are relayed;
- an unhandled upstream connectivity failure can surface as a server error.

---

#### `POST /refresh`

Refreshes an ESTORE Keycloak token set.

**Body**

```json
{
  "refresh_token": "..."
}
```

**Success - `200`**: refreshed Keycloak token JSON.

**Errors**

- `400` missing `refresh_token`;
- `401` unsuccessful refresh or token-endpoint request failure.

---

#### `POST /logout`

Ends/revokes the refresh-token session through the ESTORE Keycloak logout endpoint.

**Body**

```json
{
  "refresh_token": "..."
}
```

If Keycloak returns `204`, eStore translates it to:

**Success - `200`**

```json
{
  "message": "Logout success"
}
```

**Errors**

- `400` missing `refresh_token`;
- `401` any non-`204` Keycloak response or request failure.

### 9.2 Current customer identity and profile

#### `GET /user`

Customer bearer token required.

Returns a combined ESTORE-token and business-customer summary.

**Optional query parameter**

| Parameter | Type | Behavior |
|---|---|---|
| `username` | string | Normalized to lowercase/trimmed. If both the query value and a username-like token claim exist, they must match. |

The token username is selected from:

1. `preferred_username`;
2. `username`;
3. `email`.

The current `Customer` is resolved from the token subject in the configured store.

**Success - `200`**: `CurrentUser`.

**Errors**

- `401` missing/invalid customer token;
- `403` supplied username identifies another token user;
- `404` no current customer profile.

---

#### `POST /customer` - create

Public customer-registration route when the body does **not** contain `id`.

It creates the ESTORE Keycloak account first and then creates the mapped business `Customer` through `biz-app`.

**Typical body**

```json
{
  "username": "customer@example.com",
  "password": "customer-password",
  "email": "customer@example.com",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "billing_address": "1 Example Street",
  "shipping_address": "1 Example Street",
  "phone": "+85212345678",
  "details": "Optional profile details"
}
```

**Required behavior**

- `billing_address` must be a non-empty string and is trimmed;
- `phone` must be a non-empty string and is trimmed;
- either `username` or `email` must be present to derive the Keycloak username;
- `password` is required;
- the effective email (`email`, or `username` when email is absent) must pass eStore email validation;
- `first_name` is required;
- `last_name` is required.

Keycloak username is normalized to lowercase/trimmed. The stored Keycloak email is normalized to lowercase.

Email validation includes:

- total maximum length `254`;
- local-part maximum length `64`;
- domain maximum length `253`;
- dot-separated local atoms with no empty/leading/trailing dot;
- syntactically valid DNS-style domain labels;
- final alphabetic TLD or punycode IDN TLD.

If the normalized Keycloak username already exists, registration returns `409`.

The business customer is created with trusted ownership values:

```text
merchant_id = configured eStore merchant ID
store_id    = configured eStore store ID
username    = newly created Keycloak user ID/subject
```

The caller cannot choose those business-scope values on the create path.

If `ESTORE_CUSTOMER_ROLE` is configured, the created Keycloak user is assigned that realm role.

**Success - normally `201`**

```json
{
  "id": 42,
  "keycloak_user_id": "keycloak-subject"
}
```

The status code mirrors successful `biz-app` customer creation.

**Errors**

- `400` missing required business/customer-login data or invalid email;
- `409` duplicate Keycloak customer username;
- `500` Keycloak customer creation failure;
- `biz-app` create errors are relayed after best-effort deletion of the newly created Keycloak user.

If `first_name` or `last_name` is discovered missing after Keycloak account creation, eStore deletes the new Keycloak user before returning `400`.

---

#### `POST /customer` - update

Authenticated update mode is selected when the body contains `id`.

The route explicitly introspects the supplied bearer token and resolves the caller's current store-local customer before accepting the ID.

**Typical body**

```json
{
  "id": 42,
  "first_name": "Ada",
  "last_name": "Byron",
  "details": "Updated profile",
  "shipping_address": "2 Example Street",
  "billing_address": "2 Example Street",
  "email": "ada@example.com",
  "phone": "+85212345678"
}
```

The supplied `id` must equal the current customer's own business ID.

Writable fields are:

- `first_name`;
- `last_name`;
- `details`;
- `shipping_address`;
- `billing_address`;
- `email`;
- `phone`.

The following are rejected if present:

- `identifier`;
- `merchant_id`;
- `store_id`;
- `username`;
- `created_at`;
- `updated_at`.

`email`, when supplied, is trimmed, lowercased, and must pass the same email validator used at signup.

After a successful business profile update, eStore synchronizes `email`, `first_name`, and `last_name` to the Keycloak user when those fields were present in the request.

**Success - normally `200`**: `biz-app` customer-update JSON.

If the business update succeeds but Keycloak profile synchronization fails, eStore deliberately returns:

```json
{
  "message": "Customer updated; Keycloak profile sync failed"
}
```

with `200`, because the business profile was already committed.

**Errors**

- `400` invalid ID, forbidden system/identity field, invalid email, or no updatable fields;
- `401` missing/invalid bearer token;
- `403` attempt to update another customer;
- `404` current customer profile not found;
- other `biz-app` update errors are relayed.

Password changes are not performed by this route.

---

#### `GET /customer`

Customer bearer token required.

Resolves the current customer from token subject and returns the corresponding business profile.

**Success - `200`**: `Customer`.

**Errors:** `401` token failure; `404` profile missing; upstream errors may be relayed.

---

#### `POST /customer/update_password`

Customer bearer token required. Changes only the caller's own ESTORE Keycloak password.

**Body**

```json
{
  "current_password": "old-password",
  "new_password": "new-password"
}
```

`new_password` must be a string of at least 8 characters.

The following identity-targeting fields are rejected if present:

- `id`
- `identifier`
- `merchant_id`
- `username`
- `customer_id`
- `keycloak_user_id`
- `user_id`
- `sub`

The route retrieves the current Keycloak user, obtains its username, verifies the supplied current password through an ESTORE password grant, and only then performs the Keycloak reset-password operation.

**Success - `200`**

```json
{
  "message": "Password updated"
}
```

**Errors**

- `400` identity field supplied, missing current/new password, or new password shorter than 8 characters;
- `401` invalid customer bearer token;
- `403` current password is incorrect;
- `404` business customer profile missing;
- `500` Keycloak password operation failure.

### 9.3 Store, payment configuration, and catalog

#### `GET /payment_networks`

Public storefront configuration endpoint.

The configured merchant is resolved through `biz-app`. The merchant must use `PAYMENT_ASIA`, and its comma-separated stored network configuration must parse to a non-empty, unique list containing only supported exact network names.

**Success - `200`**: `PaymentNetworkConfiguration`.

```json
{
  "payment_gateway": "PAYMENT_ASIA",
  "payment_networks": ["CreditCard", "Fps"]
}
```

**Errors**

- `400` configured merchant does not use PaymentAsia checkout;
- `502` merchant lookup is invalid/ambiguous or the stored network list is malformed;
- scoped `biz-app` errors may be relayed.

---

#### `GET /store`

Public. Returns the one configured store.

Internally this is equivalent to calling `/store/{configured integer store id}` after startup resolution.

**Success - `200`**: `Store`.

**Errors:** `400` configured store ID unavailable; `403` scope violation; `404` store missing; upstream errors may be relayed.

---

#### `GET /store/{store_id}`

Public but restricted to the one configured store.

The route retrieves the store through scoped `biz-app` authentication and verifies both:

- `merchant_id == configured merchant id`;
- `id == configured store id`.

**Success - `200`**: `Store`.

**Errors:** `403` any other merchant/store scope; `404` missing; upstream errors may be relayed.

---

#### `GET /products`

Public approved-catalog collection.

**Supported/meaningful query parameters** inherited from `biz-app` include:

| Parameter | Type | eStore behavior |
|---|---|---|
| `store_id` | integer | Optional, but if supplied must equal the configured store. eStore then forces the configured store ID. |
| `state` | string | Omit, empty, or `A`. Any other explicit state returns `403`. eStore always sends `A` upstream. |
| `name` | string | Forwarded catalog search filter. |
| `description` | string | Forwarded catalog search filter. |
| `identifier` | string | Forwarded catalog search filter. |

After receiving the upstream list, eStore verifies every row is an object with state `A`. It then retrieves `/files?product_id=...` for every product and adds:

```json
"files": [ ... ]
```

**Success - `200`**: `Product[]`, each including `files`.

An empty approved catalog returns `[]`.

**Errors**

- `400` invalid numeric filter;
- `403` caller requests another store or non-approved state;
- `502` invalid/non-approved upstream product payload or invalid file payload;
- relevant `biz-app` errors are relayed.

---

#### `GET /product/{product_id}`

Public read of one currently approved configured-store product.

The route validates:

1. product exists through scoped `biz-app` access;
2. product is an object;
3. product `state == "A"`;
4. product store is the configured eStore store;
5. product file metadata can be retrieved.

**Success - `200`**: `Product` including `files`.

**Errors:** `403` store scope; `404` absent/non-approved product; `502` invalid upstream payload; relevant upstream errors may be relayed.

---

#### `GET /inventories`

Public product-scoped inventory read.

**Required query**

| Parameter | Type | Notes |
|---|---|---|
| `product_id` | integer | Must identify an approved product in the configured store. |

Other query values such as `location` are forwarded to `biz-app` after product scope is established.

**Success - `200`**: `Inventory[]`.

Availability is:

```text
sum(row.quantity for each returned row)
```

An empty list means zero availability.

**Errors**

- `400` missing/invalid `product_id`;
- `403` scope;
- `404` product not eStore-visible;
- upstream inventory errors are relayed.

---

#### `GET /file/{file_id}`

Public product-file metadata read.

The file's parent product is revalidated as currently approved and configured-store scoped. If the upstream file includes `merchant_id`, it must equal the configured merchant.

**Success - `200`**: `ProductFile`.

**Errors:** `403` scope; `404` file/product missing or parent no longer approved; `502` malformed upstream metadata.

---

#### `GET /image/{file_id}`

Public inline image relay.

The file metadata and parent product are scope-checked before bytes are requested from `biz-app /image/{id}`.

**Success - normally `200`**: binary response with upstream image MIME/disposition headers.

**Errors**

- scope/file/product errors as for `/file/{id}`;
- provider/business response codes are relayed;
- `502` binary relay network failure.

---

#### `GET /download`

Public attachment relay.

**Required query**

| Parameter | Type | Notes |
|---|---|---|
| `file_id` | integer | File metadata ID. Parent product must currently be approved and store-scoped. |

**Success - normally `200`**: attachment bytes and upstream filename/MIME/disposition headers.

**Errors**

- `400` missing/invalid `file_id`;
- `403` scope;
- `404` file/product missing or hidden;
- `502` binary relay network failure;
- other upstream errors are relayed.

### 9.4 Customer orders, order items, and payments

#### `GET /orders`

Customer bearer token required.

The route starts with caller query parameters, then forcibly applies:

```text
customer_id = current customer id
merchant_id = configured merchant id
store_id    = configured store id
```

A caller therefore cannot enumerate another customer's orders by supplying different scope filters.

Additional business filters such as `status`, when supported by `biz-app`, are forwarded within that forced scope.

**Success - `200`**: `Order[]`.

**Errors:** `401` token; `404` customer profile; relevant upstream validation/errors are relayed.

---

#### `GET /order/{order_id}`

Customer bearer token required.

Before returning the order, eStore requires:

- order exists;
- `order.customer_id` equals current customer ID;
- `order.merchant_id` equals configured merchant ID;
- order's store passes configured-store validation.

**Success - `200`**: `Order`.

**Errors:** `403` other customer/merchant/store; `404` missing order/profile; upstream errors may be relayed.

There is no eStore `POST /order` or `DELETE /order/{id}`. Orders are created only by trusted checkout/subscription completion workflows and are read-only to storefront customers.

---

#### `GET /order_items`

Customer bearer token required.

The route forces current customer/merchant/store filters before forwarding to `biz-app`.

Optional caller filters explicitly validated by eStore:

| Parameter | Type | Behavior |
|---|---|---|
| `order_id` | integer | Order must belong to current customer and configured store. |
| `product_id` | integer | Product must be currently approved and configured-store scoped. |

Successful payloads are normalized so every object contains `state`, defaulting to `null` only when an upstream row omitted the field.

**Success - `200`**: `OrderItem[]`.

**Errors:** `400` invalid ID filter; `401` token; `403` scope; `404` referenced resource/customer missing; upstream errors may be relayed.

---

#### `GET /order_item/{order_item_id}`

Customer bearer token required.

The order item is read through `biz-app`, and its parent order is then validated against the current customer and configured merchant/store.

**Success - `200`**: `OrderItem` with a guaranteed `state` key.

**Errors:** `403` scope; `404` missing item/order/customer; relevant upstream errors may be relayed.

There is no eStore route to create, edit, delete, or mark an order item delivered. Recurring subscription cancellation is exposed only through the dedicated customer-scoped action below.

---

#### `POST /order_item/{order_item_id}/recurring/cancel`

Customer bearer token required. Cancels one recurring subscription order item owned by the authenticated customer.

Before forwarding the action, eStore:

1. resolves the current customer from the bearer token;
2. loads the requested order item;
3. loads and validates its parent order through the existing customer/order scope checks;
4. requires that the parent order belongs to the current customer, configured merchant, and configured store;
5. only then calls `biz-app POST /order_item/{order_item_id}/recurring/cancel`.

The browser does not supply a customer ID, merchant ID, store ID, recurring merchant reference, PaymentAsia mode, or provider cancellation payload.

`biz-app` independently enforces the authenticated eStore service's merchant/store scope and performs the authoritative recurring cancellation workflow.

**Success - `200`**: the updated `OrderItem` plus an `idempotent` boolean. A newly accepted cancellation returns `idempotent: false`; an already-cancelled subscription returns `idempotent: true`.

**Errors**

- `401` missing/invalid customer bearer token;
- `403` requested order item belongs to another customer or falls outside the configured merchant/store scope;
- `404` customer, order item, or parent order missing;
- `409` order item is not recurring or the recurring schedule is already completed;
- PaymentAsia/provider and business-workflow failures are relayed from `biz-app`, including applicable `500`/`502` responses.

---

#### `GET /payments`

Customer bearer token required.

The route forces:

```text
customer_id = current customer id
merchant_id = configured merchant id
store_id    = configured store id
```

If caller supplies `order_id`, the referenced order must first pass current-customer scope validation.

Additional business filters accepted by `biz-app` may be forwarded inside the forced scope.

**Success - `200`**: `Payment[]`.

**Errors:** `400` invalid order ID; `401` token; `403` scope; `404` customer/order missing; upstream errors may be relayed.

---

#### `GET /payment/{payment_id}`

Customer bearer token required.

The payment is retrieved through `biz-app`; its `order_id` is then validated as an order belonging to the current customer and configured store.

**Success - `200`**: `Payment`.

**Errors:** `403` scope; `404` missing payment/order/customer; upstream errors may be relayed.

There is no customer-facing eStore payment create/update/delete route. Standard payment rows are created only through verified standard checkout finalization. Subscription schedule acceptance does not create a one-time payment row merely for the schedule setup.

### 9.5 Standard one-time checkout

#### `POST /checkout`

Customer bearer token required. Starts PaymentAsia Standard Hosted Payment for a cart containing **ordinary, non-recurring products only**.

**Typical body**

```json
{
  "cart": [
    {
      "product_id": 101,
      "quantity": 2
    },
    {
      "product_id": 102,
      "quantity": 1
    }
  ],
  "network": "CreditCard",
  "response_mode": "html",
  "subject": "Order summary",
  "lang": "en",
  "customer_state": "HK",
  "customer_country": "HK",
  "customer_postal_code": "000000"
}
```

#### Required fields

- `cart`: non-empty array;
- `network`: non-empty string and currently enabled for the merchant.

Each cart row must be an object with:

- integer `product_id`;
- integer `quantity > 0`.

Duplicate product IDs within one cart are rejected.

#### Server-side cart authority

For every line, eStore re-reads the product and inventory from `biz-app` and requires:

- product exists and is currently approved;
- product belongs to configured store;
- product currency is present;
- current product amount parses as decimal and is greater than zero;
- product has **no** recurring plan;
- summed current inventory is at least requested quantity.

All cart products must use the same currency.

The browser does not send trusted `unit_amount`, line `amount`, or total. eStore calculates them from the current catalog.

#### Optional fields

| Field | Behavior |
|---|---|
| `response_mode` | `html` (default) or `json`. |
| `subject` | Provider checkout subject; defaults to `Order <merchant_reference>`. |
| `lang` | PaymentAsia language; otherwise `ESTORE_CHECKOUT_LANG` may be used. |
| `customer_state` | Provider customer state; defaults to `HK`. |
| `customer_country` | Provider customer country; defaults to `HK`. |
| `customer_postal_code` | Provider postal code; defaults to `000000`. |

#### Intent creation

Before contacting PaymentAsia, eStore generates a UUID4 `merchant_reference` and creates an order-less intent through `biz-app` with status `C`.

Its immutable `intent_details` contains a trusted snapshot similar to:

```json
{
  "source": "estore_checkout",
  "merchant_reference": "uuid-reference",
  "cart": [
    {"product_id": 101, "quantity": 2}
  ],
  "line_items": [
    {
      "product_id": 101,
      "quantity": 2,
      "unit_amount": "25.00",
      "amount": "50.00"
    }
  ],
  "payment_network": "CreditCard",
  "subject": "Order uuid-reference",
  "checkout_options": {
    "lang": "en"
  },
  "checkout_kind": "ordinary"
}
```

No order exists merely because this intent was created.

#### PaymentAsia launch

The internal request to `biz-app /pa/checkout` contains:

- intent identifier;
- immutable merchant reference;
- calculated currency/amount;
- eStore-generated exact return and notify URLs;
- customer IP;
- customer name/address/phone/email with configured fallbacks;
- selected network;
- `generic: false`;
- subject and optional language.

Callback URLs are:

```text
<public-base>/checkout/return/<intent.identifier>
<public-base>/checkout/notify/<intent.identifier>
```

`public-base` is selected in this order:

1. `ESTORE_PUBLIC_BASE_URL` when configured;
2. first `X-Forwarded-Proto` + first `X-Forwarded-Host` when both are present;
3. Flask `request.url_root`.

#### HTML success - `200`

Default `response_mode=html` returns an HTML form whose action and hidden fields are supplied by the trusted `biz-app` PaymentAsia checkout response. JavaScript immediately submits the form to PaymentAsia. A `<noscript>` button is provided.

#### JSON success - `200`

With `response_mode=json`, returns `CheckoutLaunch`:

```json
{
  "checkout_id": "intent-identifier",
  "checkout_reference": "uuid-reference",
  "action_url": "https://...",
  "fields": {"...": "signed PaymentAsia form fields"}
}
```

#### Errors

- `400` missing network, invalid response mode, invalid cart, duplicate product, non-positive quantity, ordinary/subscription mismatch, invalid amount/currency, insufficient inventory, or mixed currencies;
- `401` customer bearer token failure;
- `403` network not enabled or product/store scope;
- `404` customer/product context missing;
- upstream `biz-app /pa/checkout` status/body when it rejects the launch;
- `500` checkout-intent creation failure;
- `502` successful-looking upstream launch response lacks a valid `action_url`/`fields` structure.

A successful launch is **not** proof of payment and does not create the order.

### 9.6 Subscription checkout

#### `POST /subscribe`

Customer bearer token required. Starts PaymentAsia recurring card tokenization for exactly one recurring product and quantity.

**Typical body**

```json
{
  "product_id": 201,
  "quantity": 2,
  "subject": "Annual service subscription",
  "token_valid_date": "2029-12-31"
}
```

`product_id` is required. `quantity` defaults to `1` and must be positive.

The product is re-read from the current approved configured-store catalog. eStore requires:

- a complete recurring plan;
- frequency `WEEKLY`, `MONTHLY`, or `YEARLY`;
- positive recurring interval;
- positive total execution count;
- positive current product amount;
- sufficient current inventory for requested quantity;
- currency exactly `HKD`;
- merchant PaymentAsia configuration includes `CreditCard`.

The subscription recurring start date is generated as tomorrow's calendar date in the `Asia/Hong_Kong` timezone.

#### Subscription intent

EStore generates a UUID4 merchant reference and creates a status-`C` order-less intent with immutable details similar to:

```json
{
  "source": "estore_subscription",
  "merchant_reference": "uuid-reference",
  "subscription": {
    "product_id": 201,
    "quantity": 2
  },
  "line_items": [
    {
      "product_id": 201,
      "quantity": 2,
      "unit_amount": "100.00",
      "amount": "200.00",
      "recurring_start_date": "2026-08-13",
      "recurring_frequency": "MONTHLY",
      "recurring_intervals": 1,
      "recurring_total_execution_times": 12
    }
  ],
  "payment_network": "CreditCard",
  "subject": "Annual service subscription",
  "checkout_kind": "subscription"
}
```

#### Recurring launch

EStore then calls `biz-app /recurring/checkout` with:

```json
{
  "intent_identifier": "intent-identifier",
  "customer_ip": "203.0.113.20",
  "return_url": "https://store-api.example.com/recurring/tokenization/return/intent-identifier",
  "notify_url": "https://store-api.example.com/recurring/tokenization/notify/intent-identifier",
  "payment_notify_url": "https://store-api.example.com/recurring/payment/notify",
  "subject": "Annual service subscription",
  "token_valid_date": "2029-12-31"
}
```

`token_valid_date` is included only when the caller supplied a non-empty value. Validation/interpretation of the provider token-valid date is downstream.

The internal recurring response must be a JSON object with `accepted: true` and a valid absolute `http`/`https` redirect link discoverable from the accepted result.

#### Success - `200` HTML

Returns an HTML page that immediately `window.location.replace(...)` redirects the browser to the PaymentAsia secure card-verification URL. A normal clickable `Continue` link is present as fallback.

#### Errors

- `400` missing/invalid product or quantity, invalid recurring terms, ordinary product, non-HKD recurring product, invalid price, insufficient inventory;
- `401` customer bearer token;
- `403` product/store scope or merchant has not enabled `CreditCard`;
- `404` customer/product context missing;
- upstream `biz-app /recurring/checkout` errors are relayed;
- `500` subscription-intent creation failure;
- `502` recurring request is not accepted or accepted response lacks a valid redirect URL.

Tokenization acceptance is not itself proof that a recurring schedule/order has been successfully finalized.

### 9.7 Checkout status and callback routes

#### `GET /checkout/status/{checkout_id}`

Customer bearer token required. This is the durable storefront polling endpoint for both ordinary and subscription intents.

The route loads the intent by public identifier through `biz-app /intents?identifier=...`, then requires:

- `intent.customer_id` equals current customer ID;
- `intent.store_id` equals configured store ID;
- when `order_id` exists, that order also passes current customer/store scope validation.

**Success - `200`**: `CheckoutStatus`.

`complete` is calculated as:

```text
status in {S, F, U}
```

`success` is calculated as:

```text
status == S
```

`R` is explicitly **not** terminal and must continue polling.

`payment_reference` is resolved with these fallbacks:

1. newest non-empty payment `reference` for the linked order, when an order exists;
2. trusted `system_details.request_reference`;
3. trusted `system_details.payment_reference`;
4. immutable intent `reference`;
5. immutable `intent_details.merchant_reference`.

`checkout_reference` is the storefront merchant reference from immutable intent details, falling back to intent reference.

`paymentasia_status` is read from trusted intent `system_details`.

`recurring_checkout_status` is the trusted recurring checkout state's `state` value when present.

**Errors:** `401` token; `403` checkout belongs to another customer/store; `404` customer/intent/order missing; `502` malformed scope values; upstream errors may be relayed.

---

#### `GET|POST /checkout/return/{checkout_id}`

Public browser-facing return URL for standard PaymentAsia checkout.

Callback payload extraction accepts, in priority order:

1. submitted form fields;
2. query parameters;
3. JSON object body.

If the payload contains any callback-looking key from:

- `status`
- `merchant_reference`
- `request_reference`
- `currency`
- `amount`
- `sign`

then eStore makes a best-effort attempt to forward the payload to `biz-app /paymentasia/record_payment`.

A verifier/finalization error is deliberately **not** returned as the browser page. The route logs the deferred recording condition and always renders the current durable intent state instead.

This design accommodates:

- unsigned browser navigation;
- partial provider return data;
- duplicate browser return;
- notify arriving before return;
- notify arriving after return.

**Rendered state**

| Intent status | HTTP | Page |
|---|---:|---|
| `S` | `200` | successful |
| `F` | `200` | failed |
| `U` | `202` | uncertain / reconciliation |
| other existing state | `202` | processing |
| intent unavailable | `404` | unavailable |

The HTML page emits the `PINGBIZ_ESTORE_CHECKOUT_COMPLETE` browser message but authenticated storefront code should confirm state with `/checkout/status/{checkout_id}`.

---

#### `POST /checkout/notify/{checkout_id}`

Public provider-server callback for standard checkout. Unlike the browser-return route, this route is strict.

The callback payload is forwarded to:

```text
biz-app POST /paymentasia/record_payment
```

with the route's `checkout_id` as `intent_identifier`.

`biz-app` is authoritative for signature verification, callback binding, order creation, order-item finalization, inventory commitment, payment creation/idempotency, and successful intent/order state.

**Success - `200`**

```json
{
  "ok": true,
  "payment": {
    "...": "biz-app payment finalization result"
  }
}
```

**Errors:** strict verification/finalization errors and their HTTP statuses are relayed from `biz-app`; network/proxy failure behavior follows the internal request path.

---

#### `GET|POST /recurring/tokenization/return/{checkout_id}`

Public browser return for subscription tokenization.

The callback payload uses the same form/query/JSON extraction rules.

If no non-empty `sign` field is present, the request is treated as **navigation only**. EStore does not submit it to the strict tokenization verifier. It renders the current durable recurring intent state.

Navigation-only rendering:

| Intent status | HTTP | Page |
|---|---:|---|
| `S` | `200` | subscription successful |
| `F` | `200` | subscription failed |
| `U` | `202` | uncertain/reconciling |
| other | `202` | processing |

When trusted recurring system state is `SCHEDULE_CREATING`, processing text specifically reports that the card was verified and the schedule is being created.

If `sign` is present, eStore forwards the payload to:

```text
biz-app POST /recurring/tokenization/record
```

and propagates errors rather than silently rendering around them.

After a successful signed result, eStore requires the result to indicate a pure subscription flow:

- `requires_one_time_payment` is not true;
- `one_time_payment` is absent/empty;
- exactly one `order_items` row exists;
- that row contains non-empty `recurring_merchant_reference`;
- an `order_id` exists.

Then it renders a `200` successful subscription page.

**Errors:** downstream tokenization errors are relayed; unexpected mixed/invalid result shape returns `502`.

---

#### `POST /recurring/tokenization/notify/{checkout_id}`

Public strict provider callback for subscription card tokenization/schedule setup.

Payload is forwarded to `biz-app /recurring/tokenization/record` with `intent_identifier = checkout_id`.

**Success - `200`**

```json
{
  "ok": true,
  "checkout": {
    "...": "recurring tokenization/finalization result"
  }
}
```

Errors are relayed from the authoritative business verification/finalization path.

---

#### `POST /recurring/payment/notify`

Public strict provider callback for later recurring payment executions.

There is no route-level `checkout_id`. The PaymentAsia payload carries the provider/merchant references needed by `biz-app` to resolve the persisted recurring schedule and frozen payment environment.

The payload is forwarded to:

```text
biz-app POST /recurring/payment/record
```

**Success - `200`**

```json
{
  "ok": true,
  "recurring_payment": {
    "...": "recurring execution recording result"
  }
}
```

Errors are relayed from the strict downstream verification/recording workflow.

## 10. Cross-resource workflows

### 10.1 Customer signup and login

A normal customer onboarding sequence is:

1. Browser calls public `POST /customer` without `id`.
2. eStore validates billing address, phone, login input, and email.
3. eStore creates the ESTORE Keycloak account using its confidential service credentials.
4. eStore creates the business `Customer` in its configured merchant/store and records the Keycloak subject as the business `username` mapping.
5. Browser calls `/login` or obtains an ESTORE access token through an appropriate Keycloak browser flow.
6. Browser sends the access token as `Authorization: Bearer ...`.
7. `GET /user` or `GET /customer` resolves the business profile by configured merchant + configured store + token subject.

No browser-supplied merchant/store/customer identifier establishes customer scope.

### 10.2 Public catalog and availability

A normal storefront catalog sequence is:

1. `GET /store` loads configured store presentation data.
2. `GET /payment_networks` loads enabled checkout methods.
3. `GET /products` loads only currently approved configured-store products; eStore adds each product's file metadata.
4. `/image/{file_id}` or `/download?file_id=...` retrieves bytes only after revalidating the file's approved parent product.
5. `GET /inventories?product_id=...` returns every location row for that approved product.
6. Storefront computes displayed availability as the sum of rows; `[]` means zero.

A product takedown from approved state becomes invisible to product/file/media/inventory scope validation even when a caller knows its numeric IDs.

### 10.3 Standard checkout authority flow

A complete one-time checkout is:

1. Authenticated customer selects ordinary products and quantities plus one merchant-enabled PaymentAsia network.
2. Browser calls `POST /checkout` with IDs/quantities only; it does not provide authoritative prices.
3. eStore re-reads each approved product and its inventory, rejects subscription products, validates quantity/availability, and calculates current amounts.
4. eStore creates an immutable status-`C` order-less intent containing the server-derived cart snapshot.
5. eStore calls `biz-app /pa/checkout` with the intent and exact eStore callback URLs.
6. `biz-app` validates the snapshot and payment-network rules, selects the persisted store payment mode, obtains signed hosted form fields from the correct PaymentAsia helper, and records trusted checkout launch/approval state.
7. eStore returns auto-submit HTML or structured popup launch JSON.
8. Customer completes PaymentAsia hosted checkout.
9. PaymentAsia sends server notify and may navigate the browser to the return URL.
10. Strict notify forwards the callback to `biz-app /paymentasia/record_payment` for signature verification and transactional finalization.
11. `biz-app` creates the order only on trusted completion, creates immutable order items from the snapshot, commits inventory, records the payment, and updates intent/order state.
12. Browser return renders current durable state and attempts to notify the storefront window.
13. Storefront confirms through authenticated `/checkout/status/{checkout_id}` and then reads `/order...` and `/payment...` resources.

No order is created merely because checkout was launched.

### 10.4 Subscription checkout authority flow

A complete subscription start is:

1. Authenticated customer selects exactly one approved recurring product and quantity.
2. Browser calls `POST /subscribe`.
3. eStore re-reads product/inventory, validates complete recurring terms, calculates amount, requires HKD and merchant-enabled `CreditCard`, and sets recurring start date to the next Hong Kong calendar date.
4. eStore creates an immutable status-`C` order-less subscription intent.
5. eStore calls `biz-app /recurring/checkout` with tokenization return, tokenization notify, and recurring-payment notify URLs.
6. `biz-app` selects/persists the correct PaymentAsia environment and obtains an accepted tokenization redirect.
7. eStore redirects the customer browser to PaymentAsia card verification.
8. Unsigned browser return is navigation-only; signed notify/return is submitted to `biz-app /recurring/tokenization/record`.
9. Trusted tokenization completion creates/finalizes the subscription order and exactly one recurring order item without manufacturing a one-time `Payment` row for schedule acceptance.
10. Later PaymentAsia recurring executions are sent to `/recurring/payment/notify`, which forwards them to `biz-app /recurring/payment/record` for strict verification/recording.
11. Customer can observe resulting order and recurring order-item fields through the order APIs and may cancel an owned active/non-completed recurring schedule through `POST /order_item/{order_item_id}/recurring/cancel`.

### 10.5 Browser return versus notify

Browser navigation and server notify serve different reliability roles.

For standard checkout:

- notify is strict and is the authoritative callback path;
- browser return may be unsigned, partial, duplicated, or race notify;
- browser return therefore attempts recording only when callback-looking fields exist and never turns a verifier failure into the visible browser page;
- durable status is rendered from the intent and confirmed by authenticated polling.

For recurring tokenization:

- an unsigned return is navigation-only;
- a signed return is treated as a strict tokenization callback;
- the server notify is also strict.

### 10.6 Post-purchase mutation model

The storefront API intentionally does not expose customer mutations for:

- creating/updating/deleting orders;
- creating/updating/deleting order items;
- marking delivery state;
- creating/updating/deleting one-time payments;
- reconciling recurring schedules;
- adjusting recurring payment methods or provider schedule parameters;
- altering recurring product terms after purchase.

The one supported customer lifecycle mutation is cancellation of the authenticated customer's own recurring order item through `POST /order_item/{order_item_id}/recurring/cancel`. Customer ownership is checked by eStore before the request is forwarded, while `biz-app` independently enforces the eStore service's merchant/store scope and owns the provider cancellation/state transition.

## 11. Security and tenant-isolation guarantees implemented by eStore

- Every eStore instance is bound at startup to one merchant identifier and one store identifier.
- Internal `biz-app` calls always use the merchant API key plus both configured scope identifiers.
- The merchant API key and ESTORE Keycloak client secret stay server-side.
- Customer bearer tokens are introspected through the confidential ESTORE client.
- Token introspection fails closed unless `active` is literal boolean `true` and a subject exists.
- Business customer mapping uses the ESTORE token subject within the configured store.
- Customer collection queries overwrite caller-supplied customer/merchant/store filters with trusted scope.
- Singular order/payment/order-item reads validate their parent customer/order/store context before returning data.
- Public catalog is limited to product state `A` and the configured store.
- Product files and bytes revalidate the current approved parent product before exposure.
- Product review notes are not exposed to eStore actors.
- Checkout prices and line totals are re-derived from current approved product data, not accepted from the browser.
- Checkout verifies current inventory before creating the intent/launching PaymentAsia.
- Standard carts reject recurring products; subscription checkout rejects ordinary products.
- Selected standard payment network is checked against the merchant's current PaymentAsia allow-list.
- Subscription checkout requires `CreditCard` in the allow-list.
- eStore does not connect directly to PaymentAsia helpers; trusted provider environment routing remains centralized in `biz-app`.
- Provider callback routes delegate signature/result verification to `biz-app` rather than trusting public callback reachability.
- Customer order/payment records remain read-only except for the dedicated recurring cancellation action.
- Customer recurring cancellation reuses the existing order-item -> order -> authenticated-customer ownership validation before the action is forwarded to `biz-app`.
- Checkout HTML is `no-store` and can receive an explicit frame-ancestor policy.

## 12. Integration and operational considerations

### 12.1 API shape

- There is no URL version prefix.
- Collection endpoints are not paginated by eStore.
- Most JSON business responses preserve the current `biz-app` representation rather than translating to a separate eStore resource version.
- Public and customer-scoped routes coexist in one API; clients must not infer authentication from the resource noun alone.
- `POST /customer` changes authentication requirements depending on whether `id` is present: create is public; update is customer-authenticated.

### 12.2 Customer and Keycloak consistency

- Customer signup spans Keycloak and `biz-app`; there is no distributed transaction. Rollback of a newly created Keycloak user is compensating/best-effort.
- Customer profile update commits the business change before Keycloak profile synchronization. A Keycloak sync failure is reported as a successful business update with warning text.
- Password changes affect Keycloak only and require current-password verification.
- Business `Customer.username` is a Keycloak subject mapping, not a human-readable login name.

### 12.3 Catalog and inventory

- Product/file visibility can change after a customer has loaded a page; checkout re-reads product and inventory before launch.
- Displayed availability is a sum of rows and can change between display and finalization.
- EStore prevents checkout when current summed inventory is below requested quantity, but authoritative final inventory commitment occurs downstream during trusted checkout completion.
- An empty inventory list means availability zero.

### 12.4 Payment/browser behavior

- `POST /checkout` defaults to HTML, not JSON.
- Popup integrations should request `response_mode=json` and submit the returned hosted-payment form from the popup document.
- The return page's `postMessage` uses `'*'` as the target origin; it is only a wake-up/status-delivery mechanism. The storefront must confirm authenticated checkout state rather than treating the message as payment authority.
- `ESTORE_PUBLIC_BASE_URL` is the clearest way to guarantee provider callback URLs use the intended public origin. When absent, forwarded host/proto or request origin is used.
- If proxy headers are trusted, deployment must ensure only the intended reverse proxy can supply them.

### 12.5 Subscription behavior

- `POST /subscribe` is single-product only.
- Subscription product currency must be HKD in the current eStore recurring flow.
- The recurring start date is not browser-selectable; it is the next Hong Kong calendar date.
- Only CreditCard is used for subscription tokenization.
- The public eStore surface allows an authenticated customer to cancel an owned subscription through `POST /order_item/{order_item_id}/recurring/cancel`. Change-card/adjustment and reconciliation remain outside the customer eStore API.

### 12.6 Health and dependencies

`GET /health` confirms only that the Flask process can answer the route. It does not prove:

- Keycloak reachability;
- `biz-app` reachability;
- merchant/store configuration validity after startup;
- PaymentAsia helper/gateway availability.

Deployment monitoring should add dependency-aware probes where required.

## 13. Client and integration acceptance checklist

A conforming storefront UI or integrating client should satisfy all of the following:

- Uses HTTPS in production.
- Never embeds `PINGBIZ_MERCHANT_API_KEY` or `ESTORE_CLIENT_SECRET` in browser/mobile client code.
- Uses ESTORE customer access tokens only for customer-scoped routes.
- Does not send PingBusiness merchant API-key headers from the browser.
- Treats the configured eStore deployment as one merchant/store scope and does not offer a client-side tenant selector for the same backend instance.
- Registers customers through public `POST /customer` and keeps the returned/access-token subject mapping opaque.
- Supplies non-empty billing address and phone at signup.
- Uses a deliverable syntactically valid email address at signup/profile edit.
- Uses `/customer/update_password` rather than trying to edit password through `/customer`.
- Uses `/payment_networks` to present only currently enabled standard checkout methods.
- Treats product state outside `A` as unavailable to storefront customers.
- Uses the `files` array returned on product reads and `/image`/`/download` for file bytes instead of constructing a URL from `location`.
- Computes displayed availability as the sum of `/inventories` rows and treats `[]` as zero.
- Does not send authoritative prices, totals, recurring terms, or recurring start date to `/checkout` or `/subscribe`.
- Keeps subscription products out of the ordinary cart and uses `/subscribe` for them.
- Sends one enabled exact PaymentAsia network name to `/checkout`.
- Handles both checkout launch modes: default HTML and explicit `response_mode=json`.
- Treats successful checkout launch/tokenization redirect as processing, not purchase success.
- Keeps polling `/checkout/status/{checkout_id}` while status is `C`, `R`, or another non-terminal state.
- Treats `S` as successful, `F` as failed, and `U` as uncertain/reconciliation state.
- Does not rely solely on `postMessage` delivery from the browser return page.
- Reads finalized orders/order items/payments through authenticated customer routes after completion.
- Does not attempt direct customer mutation of orders, order items, delivery state, payments, or recurring schedules except through the dedicated owned-subscription cancellation action.
- Uses `POST /order_item/{order_item_id}/recurring/cancel` only for an order item obtained within the authenticated customer's own order scope, and handles idempotent already-cancelled responses.
- Handles callback/return pages as provider/browser plumbing rather than customer-authenticated business APIs.
- Configures the reverse proxy/public base URL so PaymentAsia can reach the exact generated callback routes.
- Adds production monitoring for Keycloak, `biz-app`, and payment dependencies beyond the simple `/health` liveness endpoint.

