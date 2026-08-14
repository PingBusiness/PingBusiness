# PingBusiness eStore API specification
 
**Specification date:** 2026-07-22  
**Audience:** storefront, mobile-app, integration, QA, security, and AI code-generation teams  
**Source basis:** Canonical `app/estore/app.py` and its current `biz-app` contract from `pingbiz-master(26).zip`

## 1. Purpose and scope

`estore-app` is the merchant-hosted, customer-facing API layer for one configured PingBusiness merchant and one configured PingBusiness store. It has three independent responsibilities:

1. It authenticates and administers the merchant's **customers** against the merchant-operated ESTORE Keycloak realm.
2. It calls the central `biz-app` on behalf of that one merchant/store using server-side PingBusiness credentials and exposes only the customer-safe eStore surface, including ordinary hosted checkout and single-product recurring subscription enrollment.
3. It retrieves the merchant-maintained PaymentAsia `payment_networks` allow-list, presents those exact methods to the customer, and requires checkout to use one selected allowed network.

The browser or mobile storefront talks to `estore-app`; it must not call `biz-app` directly.

```text
Customer browser / merchant mobile app
             |
             | public calls or ESTORE customer Bearer token
             v
      merchant-hosted estore-app
       |                    |
       | ESTORE Keycloak    | server-to-server only
       | customer realm     | X-PingBiz-API-Key
       |                    | X-PingBiz-Merchant-Identifier
       |                    | X-PingBiz-Store-Identifier
       |                    v
       |                PingBusiness biz-app
       |                    |
       |                    v
       |              PingBusiness database
       |
       +---- checkout browser redirect/iframe ---- PaymentAsia
```

### Non-negotiable trust boundary

The following values are **backend secrets/configuration** and must never be embedded in JavaScript, mobile bundles, HTML, source maps, public environment files, or browser requests:

- `PINGBIZ_MERCHANT_API_KEY`
- `PINGBIZ_MERCHANT_IDENTIFIER`
- `PINGBIZ_STORE_IDENTIFIER`
- `ESTORE_CLIENT_SECRET`

`estore-app` constructs these headers itself for calls to `biz-app`:

```http
X-PingBiz-API-Key: <merchant API key>
X-PingBiz-Merchant-Identifier: <merchant UUID identifier>
X-PingBiz-Store-Identifier: <store UUID identifier>
```

`biz-app` validates all three, verifies that the merchant is active, verifies the API-key hash, verifies that the store belongs to the merchant, and then creates a store-scoped actor with the logical `ESTORE_ROLE`.

## 2. Base URL and transport

Examples use:

```text
https://store-api.example.com
```

All production traffic should use HTTPS. JSON requests use:

```http
Content-Type: application/json
Accept: application/json
```

Exceptions:

- `POST /checkout` returns auto-submit `text/html` by default or structured JSON when `response_mode` is `json`.
- `POST /subscribe` returns redirect `text/html`.
- checkout and tokenization browser-return routes return visible `text/html`; notify routes return JSON.
- `GET /image/{file_id}` returns image bytes.
- `GET /download` returns attachment bytes.
- Payment-gateway callback routes accept form data, and the notify route also accepts JSON.

## 3. Deployment configuration that affects the API

### Required environment variables

| Variable | Purpose |
|---|---|
| `PINGBIZ_MERCHANT_IDENTIFIER` | Public UUID-like identifier of the one PingBusiness merchant represented by this deployment. |
| `PINGBIZ_STORE_IDENTIFIER` | Public UUID-like identifier of the one PingBusiness store represented by this deployment. |
| `PINGBIZ_MERCHANT_API_KEY` | Secret merchant API key used only by `estore-app` when calling `biz-app`. |
| `ESTORE_CLIENT_SECRET` | Confidential ESTORE Keycloak client secret used for token introspection, refresh, logout, and customer administration. |

The application resolves the configured merchant and store through `biz-app` during startup. Startup fails if either lookup fails, either lookup is ambiguous, or the store does not belong to the merchant. Payment-network configuration is read dynamically from the current merchant record rather than from an eStore environment default.

### Important optional variables

| Variable | Default | Effect |
|---|---:|---|
| `ESTORE_APP_PORT` | `5000` | Flask listening port. |
| `BIZ_APP_BASE_URL` | `http://biz-app:5000` | Internal PingBusiness API base URL. |
| `ESTORE_REALM` | `ESTORE` | Customer Keycloak realm. |
| `ESTORE_CLIENT_ID` | `estore-app` | Confidential ESTORE Keycloak client. |
| `ESTORE_KC_SERVER_URL` | `KC_SERVER_URL` or `http://k-keycloak:8080/auth/` | Keycloak root used for token and admin URLs. |
| `ESTORE_TOKEN_URL` | derived | Override for the realm token endpoint. |
| `ESTORE_LOGOUT_URL` | derived | Override for the realm logout endpoint. |
| `ESTORE_CUSTOMER_ROLE` | empty | Optional realm role assigned to newly created customers. |
| `ESTORE_PUBLIC_BASE_URL` | request-derived | Public origin used to construct checkout return and notify URLs. Set this behind reverse proxies unless forwarded host/protocol are guaranteed correct. |
| `ESTORE_CHECKOUT_LANG` | empty | Optional default PaymentAsia language. |
| `ESTORE_CHECKOUT_FRAME_ANCESTORS` | empty | Optional CSP `frame-ancestors` value on checkout HTML/return pages. |
| `ESTORE_TRUST_PROXY_HEADERS` | `true` | Enables `ProxyFix` for forwarded host/protocol/port information. |
| `DEV_MODE` | `true` | In development, CORS is open. |
| `ESTORE_ALLOWED_ORIGINS` | empty | Comma-separated production CORS origins when `DEV_MODE=false`. |

## 4. Authentication models

### 4.1 Public storefront access

The payment-network list, catalog, store, media, customer registration, health, login, refresh, logout, and payment callbacks have no customer bearer-token decorator. This does not make PingBusiness credentials public; those credentials remain inside `estore-app`.

### 4.2 Customer bearer authentication

Protected customer routes require:

```http
Authorization: Bearer <ESTORE access token>
```

`estore-app` introspects the token against the merchant's ESTORE Keycloak realm and fails closed unless:

- `active` is the literal JSON boolean `true`;
- `sub` is present and non-empty.

Missing, null, false, string, numeric, or other non-boolean `active` values are rejected. The `sub` claim is the authoritative customer identity. The matching PingBusiness customer record is resolved with the configured merchant ID, configured store ID, and `BCustomers.username == token.sub`.

A login name or email is therefore **not** the PingBusiness customer-mapping key. On registration, `estore-app` creates the Keycloak user and stores the resulting Keycloak user ID in the PingBusiness `username` column.

### 4.3 Payment callbacks

`/checkout/return/{checkout_id}`, `/checkout/notify/{checkout_id}`, `/recurring/tokenization/return/{checkout_id}`, `/recurring/tokenization/notify/{checkout_id}`, and `/recurring/payment/notify` are intentionally not customer-bearer protected because PaymentAsia must call them. Callback payloads are forwarded through the authenticated server-to-server channel to `biz-app`, which asks the internal payment helper to verify signatures and binds the normalized result to a store-scoped intent, recurring order item, or execution record. Unsigned browser navigation to a return URL is treated only as navigation/status display and is never accepted as proof of payment or tokenization.

## 5. General response and error conventions

### JSON errors

Errors created directly by `estore-app` normally use:

```json
{
  "error": "Human-readable message"
}
```

Some proxied `biz-app` responses use `message`, `details`, `raw`, or additional fields. A client should obtain an error message in this order:

1. `error.error`
2. `error.message`
3. `message`
4. `raw`
5. HTTP status text

### Empty responses

Some not-found reads from `biz-app` use HTTP `204 No Content`. `estore-app` usually converts scoped validation misses to `404`, but a client should still tolerate a bodyless `204` from proxied operations.

### Date/time values

Database timestamps are returned as JSON strings by Flask. Treat them as opaque date/time strings parseable by the platform rather than relying on one display format.

### Monetary values

Monetary fields are serialized as fixed-point strings with two decimal places, for example:

```json
"29.90"
```

Do not perform financial calculations with binary floating point. Use decimal arithmetic where correctness matters.

### Identifiers

- Numeric `id` fields are internal integer primary keys used by most route paths.
- `identifier` fields are public UUID-like strings, normally up to 36 characters.
- A checkout ID is the payment-intent `identifier`, not its integer `id`.

## 6. Resource schemas

Fields marked “nullable” may be absent or `null`, depending on upstream data and serialization.

### 6.1 `AuthTokenResponse`

The login and refresh endpoints return the Keycloak token response. Common fields are:

| Field | Type | Notes |
|---|---|---|
| `access_token` | string | Customer bearer token. |
| `refresh_token` | string | May be absent depending on realm/client policy. |
| `expires_in` | integer | Access-token lifetime in seconds. |
| `refresh_expires_in` | integer | Refresh-token lifetime in seconds. |
| `token_type` | string | Normally `Bearer`. |
| `scope` | string | Realm/client dependent. |
| other fields | any | Keycloak may add session, policy, or identity fields. |

### 6.2 `CurrentUser`

```json
{
  "sub": "a-keycloak-user-id",
  "username": "customer@example.com",
  "email": "customer@example.com",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "customer_id": 42,
  "customer": { "...": "Customer" }
}
```

### 6.3 `Customer`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | PingBusiness customer ID. |
| `identifier` | string | Public customer identifier. |
| `merchant_id` | integer | Deployment-scoped merchant ID. Read-only to the storefront. |
| `store_id` | integer | Deployment-scoped store ID. Read-only to the storefront. |
| `first_name` | string | Required on creation. |
| `last_name` | string | Required on creation. |
| `details` | string, nullable | Arbitrary text; may contain JSON but is not guaranteed to. |
| `shipping_address` | string, nullable | Free-form. |
| `billing_address` | string, nullable | Free-form. |
| `email` | string, nullable | Also synchronized to Keycloak on update. |
| `phone` | string, nullable | Database limit is 16 characters. |
| `username` | string, nullable | In eStore-created records this is the Keycloak user ID, not the login name. |
| `created_at` | date/time string | Read-only. |
| `updated_at` | date/time string, nullable | Read-only. |

### 6.4 `Store`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Configured store numeric ID. |
| `identifier` | string | Configured store UUID-like identifier. |
| `merchant_id` | integer | Owning merchant. |
| `name` | string | Store name. |
| `details` | string, nullable | Store description/configuration text. |
| `mode` | string | `T` = test; `L` = live. |
| `created_at` | date/time string | Read-only. |
| `updated_at` | date/time string, nullable | Read-only. |

### 6.5 `Product`

Only approved products are exposed.

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Product numeric ID. |
| `identifier` | string, nullable | Public product identifier/SKU-like value. |
| `store_id` | integer | Always the configured store. |
| `name` | string | Product name. |
| `details` | string, nullable | Arbitrary product details. |
| `description` | string, nullable | Product description. |
| `amount` | decimal string | Current unit amount. |
| `currency` | string | Three uppercase letters. |
| `recurring_frequency` | string, nullable | `WEEKLY`, `MONTHLY`, or `YEARLY`; null for an ordinary product. |
| `recurring_intervals` | integer, nullable | Positive schedule interval count. |
| `recurring_total_execution_times` | integer, nullable | Positive execution count, subject to backend frequency limits. |
| `state` | string | Always `A` through the eStore API. |
| `files` | `ProductFile[]` | Added by `estore-app` to product list and detail responses. |
| `created_at` | date/time string | Read-only. |
| `updated_at` | date/time string, nullable | Read-only. |

`review_notes` is deliberately excluded for the eStore actor.

### 6.6 `ProductFile`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | File ID used by image/download routes. |
| `merchant_id` | integer | Owning merchant. |
| `product_id` | integer | Parent product. |
| `name` | string | Download filename. |
| `description` | string, nullable | The reference UI recognizes `__PINGBIZ_MAIN_TITLE_IMAGE__` as the preferred primary image marker. |
| `location` | string | Server storage location metadata. Do not construct a public URL from it. |
| `size` | integer | Bytes. |
| `mime_type` | string | Used to identify images and response content type. |
| `created_at` | date/time string | Read-only. |

Use `/image/{id}` or `/download?file_id={id}`. Never expose or concatenate `location` into a client URL.

### 6.7 `Inventory`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Inventory-row ID. |
| `product_id` | integer | Parent product. |
| `quantity` | integer | Quantity at this location. It can be zero or negative; calculate availability using the sum of all returned rows. |
| `location` | string | Empty string represents the default location. |
| `updated_at` | date/time string, nullable | Read-only. |

An empty array means total availability is zero.

### 6.8 `Order`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Order ID. |
| `identifier` | string | Public order identifier. |
| `merchant_id` | integer | Deployment merchant. |
| `customer_id` | integer | Current customer. |
| `store_id` | integer | Deployment store. |
| `status` | string | Single-letter status. Known storefront labels include `N`, `P`, `C`, `R`, `S`, `F`, `U`. |
| `currency` | string | Three uppercase letters. |
| `subtotal_amount` | decimal string | Checkout subtotal. |
| `total_amount` | decimal string | Checkout total. |
| `details` | string, nullable | Server-generated/free-form metadata. |
| `created_at` | date/time string | Read-only. |
| `updated_at` | date/time string, nullable | Read-only. |

Orders are created only after verified successful payment and are read-only to storefront customers.

### 6.9 `OrderItem`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Order-item ID. |
| `order_id` | integer | Parent order. |
| `order_status` | string, nullable | Parent order status added by `biz-app`. |
| `product_id` | integer | Product sold. |
| `quantity` | integer | Positive quantity. |
| `unit_amount` | decimal string | Checkout-time unit amount. |
| `amount` | decimal string | Checkout-time line total. |
| `recurring_start_date` | ISO-8601 date string, nullable | Subscription start date. |
| `recurring_frequency` | string, nullable | Copied subscription frequency. |
| `recurring_intervals` | integer, nullable | Copied subscription interval. |
| `recurring_total_execution_times` | integer, nullable | Copied execution count. |
| `recurring_merchant_reference` | string, nullable | Provider schedule reference. |
| `recurring_status` | string, nullable | `PENDING`, `ACTIVE`, `CANCELLED`, `COMPLETED`, `ERROR`, or `UNKNOWN`. |
| `subscription_details` | object, nullable | Sanitized subscription audit data; raw tokenization/card/signature secrets are excluded by `biz-app`. |
| `state` | string or null | `D` = delivered; `null` = not marked delivered. `estore-app` ensures this key exists. |
| `details` | string, nullable | Server metadata. |
| `created_at` | date/time string | Read-only. |
| `updated_at` | date/time string, nullable | Read-only. |

### 6.10 `Payment`

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Payment ID. |
| `identifier` | string | Public payment identifier. |
| `order_id` | integer | Parent order. |
| `merchant_id` | integer | Deployment merchant. |
| `store_id` | integer | Deployment store. |
| `currency` | string | Three uppercase letters. |
| `amount` | decimal string | Verified amount. |
| `status` | string | Single-letter payment status; successful records use `S`. |
| `reference` | string, nullable | Provider/payment reference. |
| `details` | string, nullable | Provider metadata, normally JSON text. |
| `created_at` | date/time string | Read-only. |

### 6.11 `PaymentNetworkConfiguration`

```json
{
  "payment_gateway": "PAYMENT_ASIA",
  "payment_networks": ["CreditCard", "Fps", "PayMe"]
}
```

`payment_networks` is a non-empty JSON array derived from the merchant record's canonical comma-separated `TEXT` value. Valid exact values are `Alipay`, `Wechat`, `CUP`, `CreditCard`, `Fps`, `Octopus`, and `PayMe`. `UserDefine` is not returned because the merchant's exact allowed subset must be enforced.

For `Octopus`, the trusted checkout total must be an exact multiple of HKD 0.10. The eStore derives the total normally, and `biz-app` is the authoritative guard that rejects incompatible totals before a signed launch form is issued.

### 6.12 `CheckoutStatus`

```json
{
  "checkout_id": "intent-uuid",
  "complete": true,
  "success": true,
  "status": "S",
  "order_id": 123,
  "payment_reference": "provider-reference-or-checkout-reference",
  "checkout_reference": "storefront-merchant-reference",
  "paymentasia_status": "1",
  "recurring_checkout_status": null
}
```

`complete` is true only for intent states `S`, `F`, or `U`. State `R` means redirected/processing and is not terminal. `recurring_checkout_status` surfaces the detailed recurring workflow state when the intent is a subscription.

## 7. Endpoint summary

| Method | Path | Customer auth | Response |
|---|---|---:|---|
| `GET` | `/health` | No | JSON |
| `POST` | `/login` | No | Keycloak token JSON |
| `POST` | `/logout` | No bearer; refresh token in body | JSON |
| `POST` | `/refresh` | No bearer; refresh token in body | Keycloak token JSON |
| `GET` | `/user` | Yes | `CurrentUser` |
| `POST` | `/customer` | Create: no; update: yes | JSON |
| `GET` | `/customer` | Yes | `Customer` |
| `POST` | `/customer/update_password` | Yes | JSON |
| `GET` | `/payment_networks` | No | `PaymentNetworkConfiguration` |
| `GET` | `/store` | No | `Store` |
| `GET` | `/store/{store_id}` | No | `Store` |
| `GET` | `/products` | No | `Product[]` |
| `GET` | `/product/{product_id}` | No | `Product` |
| `GET` | `/inventories` | No | `Inventory[]` |
| `GET` | `/file/{file_id}` | No | `ProductFile` |
| `GET` | `/image/{file_id}` | No | Image bytes |
| `GET` | `/download` | No | Attachment bytes |
| `GET` | `/orders` | Yes | `Order[]` |
| `GET` | `/order/{order_id}` | Yes | `Order` |
| `GET` | `/order_items` | Yes | `OrderItem[]` |
| `GET` | `/order_item/{order_item_id}` | Yes | `OrderItem` |
| `POST` | `/order_item/{order_item_id}/recurring/cancel` | Yes | `OrderItem` |
| `GET` | `/payments` | Yes | one-time `Payment[]` |
| `GET` | `/payment/{payment_id}` | Yes | one-time `Payment` |
| `POST` | `/checkout` | Yes | HTML or launch JSON |
| `POST` | `/subscribe` | Yes | Tokenization redirect HTML |
| `GET` | `/checkout/status/{checkout_id}` | Yes | `CheckoutStatus` |
| `GET`, `POST` | `/checkout/return/{checkout_id}` | Payment/browser callback | Visible status HTML |
| `POST` | `/checkout/notify/{checkout_id}` | Payment callback | JSON |
| `GET`, `POST` | `/recurring/tokenization/return/{checkout_id}` | Browser/tokenization callback | Visible status HTML |
| `POST` | `/recurring/tokenization/notify/{checkout_id}` | Tokenization callback | JSON |
| `POST` | `/recurring/payment/notify` | Recurring payment callback | JSON |

## 8. Endpoint reference

### 8.1 Health

#### `GET /health`

Returns service liveness.

**Success — `200`**

```json
{
  "status": "ok",
  "service": "estore-app"
}
```

---

### 8.2 Authentication

#### `POST /login`

Convenience password-grant login against the merchant's ESTORE Keycloak realm. Authorization Code + PKCE may be used directly with Keycloak by a production browser client, but the resulting ESTORE token is still sent to protected `estore-app` routes.

**Body**

```json
{
  "username": "customer@example.com",
  "password": "customer-password"
}
```

| Field | Required | Notes |
|---|---:|---|
| `username` | Yes | Keycloak username; the reference UI normalizes registration names to lowercase. |
| `password` | Yes | Customer password. |

**Success — normally `200`**: `AuthTokenResponse` from Keycloak.  
**Errors:** `400` when a field is missing; otherwise the Keycloak status and body are relayed.

#### `POST /refresh`

**Body**

```json
{
  "refresh_token": "..."
}
```

**Success — `200`**: refreshed Keycloak token response.  
**Errors:** `400` missing token; `401` refresh failure or upstream request failure.

#### `POST /logout`

**Body**

```json
{
  "refresh_token": "..."
}
```

**Success — `200`**

```json
{
  "message": "Logout success"
}
```

**Errors:** `400` missing token; `401` unsuccessful Keycloak logout.

#### `GET /user`

Requires customer bearer authentication. Returns token identity plus the matching customer profile.

**Optional query**

| Parameter | Type | Behavior |
|---|---|---|
| `username` | string | Optional login name. If both this value and a username/email claim exist in the token, they must match after lowercase/trim normalization. |

**Success — `200`**: `CurrentUser`.  
**Errors:** `401` token error; `403` attempted cross-user read; `404` no PingBusiness customer profile for the token `sub`.

---

### 8.3 Customer account

#### `POST /customer` — create

Creation mode is selected when the body does **not** contain `id`. The route creates the Keycloak user first, then creates the store-scoped PingBusiness customer. If the business-record creation fails, it attempts to delete the new Keycloak user.

**Body**

```json
{
  "username": "customer@example.com",
  "email": "customer@example.com",
  "password": "at-least-an-appropriate-realm-password",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "phone": "+85212345678",
  "shipping_address": "...",
  "billing_address": "...",
  "details": "Optional text or JSON string"
}
```

| Field | Required | Notes |
|---|---:|---|
| `username` or `email` | Yes | Login name is normalized to lowercase. If `username` is omitted, `email` is used. |
| `password` | Yes | No local minimum is enforced here; Keycloak policy may impose one. The reference UI requires 8 characters. |
| `first_name` | Yes | Required before the business record is created. |
| `last_name` | Yes | Required before the business record is created. |
| `email` | No | Defaults to the normalized username. |
| other profile fields | No | Passed into the customer profile. |

Merchant ID, store ID, business username, identifiers, and timestamps are derived server-side.

**Success — normally `201`**

```json
{
  "id": 42,
  "keycloak_user_id": "6ff8..."
}
```

**Errors:** `400` validation; `409` login already exists; `500` Keycloak/admin failure; proxied business errors.

> Production deployments should put registration rate limiting, abuse controls, email verification, password policy, and bot protection in front of this public route. Those controls are not implemented by the canonical route itself.

#### `POST /customer` — update

Update mode is selected when `id` is present. A bearer token is required, and `id` must equal the customer mapped from the token `sub`.

**Allowed body fields**

```json
{
  "id": 42,
  "first_name": "Ada",
  "last_name": "Lovelace",
  "details": "...",
  "shipping_address": "...",
  "billing_address": "...",
  "email": "new@example.com",
  "phone": "+85212345678"
}
```

Forbidden fields include `identifier`, `merchant_id`, `store_id`, `username`, `created_at`, and `updated_at`.

**Success — `200`**

Usually:

```json
{
  "message": "Customer updated successfully"
}
```

If the PingBusiness update succeeds but Keycloak profile synchronization fails:

```json
{
  "message": "Customer updated; Keycloak profile sync failed"
}
```

The caller should re-read `GET /customer` rather than assume the update response is a complete customer object.

#### `GET /customer`

Requires customer bearer authentication.

**Success — `200`**: `Customer`.  
**Errors:** `401`; `404` no mapped profile; proxied errors.

#### `POST /customer/update_password`

Requires customer bearer authentication. Identity selectors are prohibited.

**Body**

```json
{
  "current_password": "old-password",
  "new_password": "new-password-at-least-8-characters"
}
```

**Success — `200`**

```json
{
  "message": "Password updated"
}
```

**Errors:** `400` missing/short input or supplied identity fields; `403` current password invalid; `500` update failure.

---

### 8.4 Store and catalog

#### `GET /payment_networks`

Returns the currently configured PaymentAsia choices for this merchant. No customer bearer token is required because the result is storefront presentation data, not a credential.

`estore-app` reads the configured merchant through authenticated server-to-server `biz-app` access, requires `payment_gateway == PAYMENT_ASIA`, parses the merchant's comma-separated `payment_networks`, and validates every entry.

**Success — `200`**: `PaymentNetworkConfiguration`.

```json
{
  "payment_gateway": "PAYMENT_ASIA",
  "payment_networks": ["CreditCard", "Fps", "PayMe"]
}
```

**Errors:** `400` merchant is not configured for PaymentAsia; proxied `biz-app` authentication/scope errors when merchant lookup fails; `502` when the merchant lookup is ambiguous/malformed or the stored network configuration is empty, duplicated, or contains unsupported values.

The storefront should call this endpoint when presenting checkout methods and should not hard-code a network list.

#### `GET /store`

Returns the one configured store.

**Success — `200`**: `Store`.

#### `GET /store/{store_id}`

`store_id` must be the configured numeric store ID. This is not a cross-store lookup facility.

**Success — `200`**: `Store`.  
**Errors:** `404` missing; `403` outside configured merchant/store scope.

#### `GET /products`

Returns approved products from the configured store and attaches each product's file metadata.

**Query parameters**

| Parameter | Type | Behavior |
|---|---|---|
| `name` | string | Case-insensitive substring match. |
| `description` | string | Case-insensitive substring match. |
| `identifier` | string | Case-insensitive substring match. |
| `state` | string | May be omitted, blank, or `A`. Any other value returns `403`. `estore-app` always forwards `A`. |
| `store_id` | integer | Optional; if supplied it must equal the configured store. The server always enforces the configured store. |
| `recurring` | boolean-like string | Optional filter forwarded to `biz-app`: true selects subscription products; false selects ordinary products. |

**Success — `200`**: `Product[]`, sorted by product name by `biz-app`. Each product contains `files`.

**Defensive behavior:** if `biz-app` returns a non-list, malformed row, or non-approved product, `estore-app` returns `502` rather than exposing it.

#### `GET /product/{product_id}`

Returns one approved product from the configured store, with `files`.

**Success — `200`**: `Product`.  
**Errors:** `404` absent or not approved; `403` outside store; `502` invalid upstream shape.

#### `GET /inventories`

**Required query**

| Parameter | Type | Notes |
|---|---|---|
| `product_id` | integer | Required; product must be approved and belong to the configured store. |
| `location` | string | Optional case-insensitive substring filter forwarded to `biz-app`. |

**Success — `200`**: `Inventory[]`, ordered by product, location, and row ID. Sum all rows for total availability. Empty array means zero.

**Errors:** `400` missing/non-integer product ID; `404` product absent/not approved; `403` outside scope.

#### `GET /file/{file_id}`

Returns metadata for a file whose parent product is approved and in scope.

**Success — `200`**: `ProductFile`.  
**Errors:** `404` missing or parent unavailable; `403` outside scope; `502` invalid upstream data.

#### `GET /image/{file_id}`

Returns an inline image response. The parent product must be approved and in scope, and the file MIME type must begin with `image/`.

**Success — `200`**: bytes with the stored image MIME type and an inline content disposition.  
**Errors:** JSON `400` if not an image; `404` metadata or stored bytes missing; `502` relay failure.

In browser applications, request this endpoint as a `Blob`, create an object URL, and revoke the URL when no longer used.

#### `GET /download`

**Required query**

| Parameter | Type | Notes |
|---|---|---|
| `file_id` | integer | Required; parent product must be approved and in scope. |

**Success — `200`**: bytes with attachment content disposition and the stored filename.  
**Errors:** `400`, `403`, `404`, or `502` as applicable.

---

### 8.5 Orders and order items

All routes in this section require customer bearer authentication. `estore-app` overwrites customer, merchant, and store filters with the current authenticated scope. A caller cannot use query parameters to read another customer's records.

#### `GET /orders`

**Optional query**

| Parameter | Type | Notes |
|---|---|---|
| `status` | one-letter string | Exact order-status filter. |

**Success — `200`**: `Order[]`, newest first.

#### `GET /order/{order_id}`

The order must belong to the current customer, merchant, and store.

**Success — `200`**: `Order`.  
**Errors:** `404` missing; `403` outside customer or deployment scope.

#### `GET /order_items`

**Optional query**

| Parameter | Type | Notes |
|---|---|---|
| `order_id` | integer | Prevalidated as an order of the current customer. |
| `product_id` | integer | Prevalidated as a currently approved product in the configured store. |

**Success — `200`**: `OrderItem[]`, oldest first within the result set. Every row contains `state`, including `null` when not delivered.

#### `GET /order_item/{order_item_id}`

The parent order must belong to the current customer and configured scope.

**Success — `200`**: `OrderItem`.

#### `POST /order_item/{order_item_id}/recurring/cancel`

Cancels the customer's own recurring subscription. The parent order must belong
to the current customer and configured scope; `estore-app` verifies that before
proxying to biz-app. The request takes no body.

**Success — `200`**: the serialized `OrderItem`, with `recurring_status` moved to
`CANCELLED`.

Any non-2xx means nothing changed and the subscription is still active, so the
call is safe to retry. Cancelling stops future collections; it is not a refund
and does not alter payments already taken.

#### Deliberately absent writes

The customer API does not expose:

- `POST /order`
- `DELETE /order/{id}`
- `POST /order_item`
- `DELETE /order_item/{id}`
- delivery-state mutation

Orders and order items are finalized by the verified checkout transaction. The
only customer-initiated write is
`POST /order_item/{order_item_id}/recurring/cancel`, which moves
`recurring_status` to `CANCELLED` on the customer's own subscription and changes
nothing else. Order and order-item records are otherwise immutable from the
customer storefront.

---

### 8.6 Payments

All routes require customer bearer authentication and are scoped through the payment's parent order.

#### `GET /payments`

**Optional query**

| Parameter | Type | Notes |
|---|---|---|
| `order_id` | integer | Parent order; prevalidated as current-customer scope. |
| `status` | one-letter string | Exact payment status. |
| `currency` | 3-letter string | Normalized to uppercase. |
| `identifier` | string | Case-insensitive substring match. |
| `reference` | string | Case-insensitive substring match. |
| `created_from` | ISO-8601 date/time | Inclusive lower bound. Timezone-aware input is normalized to UTC. |
| `created_to` | ISO-8601 date/time | Exclusive upper bound. |

**Success — `200`**: `Payment[]`, newest first.

#### `GET /payment/{payment_id}`

The payment's order must belong to the current customer and configured scope.

**Success — `200`**: `Payment`.

#### Deliberately absent writes

There is no customer-facing `POST /payment`. One-time payment rows are created only after a verified Standard Hosted Payment result. Subscription schedule acceptance does not create a one-time `Payment` row, and recurring execution records are not exposed as separate estore-app endpoints in this source snapshot; customers observe subscription state through their order items.

---

### 8.7 Ordinary checkout and recurring subscriptions

#### `POST /checkout`

Requires customer bearer authentication. This endpoint accepts ordinary products only. A product with recurring terms is rejected with guidance to use `/subscribe`.

**Body**

```json
{
  "cart": [
    { "product_id": 101, "quantity": 2 },
    { "product_id": 205, "quantity": 1 }
  ],
  "network": "CreditCard",
  "response_mode": "json",
  "lang": "en",
  "subject": "Optional payment subject",
  "customer_state": "HK",
  "customer_country": "HK",
  "customer_postal_code": "000000"
}
```

| Field | Required | Validation/default |
|---|---:|---|
| `cart` | Yes | Non-empty array. Each line has integer `product_id` and integer `quantity > 0`. Duplicate products are rejected. |
| `network` | Yes | Exact value from current `GET /payment_networks`; disabled values return `403`. |
| `response_mode` | No | `html` (default) or `json`. |
| `lang` | No | Body value, otherwise `ESTORE_CHECKOUT_LANG` when configured. |
| `subject` | No | Defaults to `Order <merchant_reference>`. |
| `customer_state` | No | Defaults to `HK`. |
| `customer_country` | No | Defaults to `HK`. |
| `customer_postal_code` | No | Defaults to `000000`. |

The server ignores client prices, totals, currency, identity/address fields, callback URLs, and merchant reference. It re-reads approved products, rejects subscription products, validates one currency and current inventory, and derives prices and totals using decimal arithmetic.

It creates a globally unique merchant reference and an order-less `C` intent containing immutable `intent_details` with `checkout_kind: ordinary`, the selected payment network, original cart, and complete line-item snapshot. It never supplies `order_id` and never updates the intent after creation.

`biz-app` independently revalidates merchant network configuration, order-less scope, current product state and price, callback paths, and the immutable snapshot. It creates one trusted Standard checkout claim and stores the exact signed launch response. An identical internal retry returns the saved response rather than issuing another launch.

For `Octopus`, the total must be an exact multiple of HKD 0.10. An incompatible cart total is rejected by `biz-app` with `400`; no signed PaymentAsia form or trusted checkout claim is created.

**HTML success - `200 text/html`**

Default response is an auto-submitting PaymentAsia form. The document includes `data-checkout-id` and `data-checkout-reference`, has `Cache-Control: no-store`, and may include the configured frame-ancestors CSP.

**JSON success - `200 application/json`**

```json
{
  "checkout_id": "intent-uuid",
  "checkout_reference": "merchant-reference-uuid",
  "action_url": "https://payment-gateway.example/...",
  "fields": { "signed_field": "value" }
}
```

JSON mode is intended for popup clients that create a normal popup document and submit the returned fields directly. It avoids relying on a top-level blob URL after navigation crosses to PaymentAsia.

**Errors:** `400` request/cart/currency/inventory/response-mode validation, Octopus increment, or `biz-app` checkout validation; `401` auth; `403` network disabled; `404` customer/product; `409` conflicting or terminal trusted checkout; `500` intent creation; `502` malformed/upstream gateway response.

#### Obtaining `checkout_id`

In HTML mode, parse the hidden `return_url` or `notify_url`, or read the `data-checkout-id` attribute. In JSON mode, use `checkout_id` directly.

---

#### `POST /subscribe`

Requires customer bearer authentication. Starts a recurring subscription for exactly one recurring product and quantity; subscription products are not accepted in the ordinary cart.

**Body**

```json
{
  "product_id": 301,
  "quantity": 1,
  "subject": "Subscription Example Product",
  "token_valid_date": "2027-07-21"
}
```

| Field | Required | Validation/default |
|---|---:|---|
| `product_id` | Yes | Must be approved, in the configured store, and have a complete recurring plan. |
| `quantity` | No | Positive integer; defaults to `1`. |
| `subject` | No | Defaults from product name/reference. |
| `token_valid_date` | No | Forwarded to PaymentAsia tokenization when supplied. |

The server requires:

- product currency `HKD`;
- sufficient current inventory;
- merchant-enabled `CreditCard` network;
- current product price and recurring plan;
- a start date of the next calendar day in Asia/Hong_Kong.

It creates an order-less intent with one recurring line and calls `biz-app /recurring/checkout`. The returned HTML immediately navigates the payment window to the validated PaymentAsia tokenization redirect link and also provides a manual Continue link.

**Success — `200 text/html`** with `Cache-Control: no-store`.

**Errors:** `400` missing/invalid/non-recurring/HKD/inventory input; `401` auth; `403` CreditCard disabled; `404` customer/product; `500` intent creation; `502` malformed or rejected tokenization launch response.

---

#### `GET /checkout/status/{checkout_id}`

Requires customer bearer authentication and validates both customer and configured-store scope. It reports ordinary and subscription intents.

**Success — `200`**: `CheckoutStatus`.

| Intent status | Meaning |
|---|---|
| `C` | Created. |
| `R` | Redirected/processing; not terminal. |
| `S` | Successful; terminal. |
| `F` | Failed; terminal. |
| `U` | Unknown/reconciliation required; terminal for UI waiting. |

`checkout_reference` is the storefront reference created before gateway redirect. `payment_reference` prefers the final one-time `Payment.reference` when an order/payment exists and otherwise falls back safely to verified/intent references. For subscriptions, `recurring_checkout_status` exposes the detailed recurring state.

---

#### `GET|POST /checkout/return/{checkout_id}`

PaymentAsia one-time browser return. Form, query, or JSON-like callback fields are accepted by the shared payload reader.

When callback-looking fields are present, the route makes a best-effort call to verified payment recording. It never displays a verifier/proxy error as the customer page. It then renders the durable intent state:

- `S`: successful HTML, `200`;
- `F`: failed HTML, `200`;
- `U`: uncertain/reconciliation HTML, `202`;
- other states: processing HTML, `202`;
- unavailable intent: recovery guidance, `404` HTML.

The page displays order/payment information when available and posts `PINGBIZ_ESTORE_CHECKOUT_COMPLETE` to `window.parent` and `window.opener` immediately and again after short delays. The message is only a wake-up signal; authenticated `/checkout/status` is authoritative. The page does not close its own window.

---

#### `POST /checkout/notify/{checkout_id}`

PaymentAsia one-time server notification. Forwards the raw payload to verified `biz-app /paymentasia/record_payment`.

**Success — `200`**

```json
{
  "ok": true,
  "payment": { "payment_id": 77, "order_id": 123, "status": "S", "idempotent": false }
}
```

A verified failure updates the intent to `F` and returns a result without creating a one-time `Payment` row. Exact successful/failure replays are idempotent.

---

#### `GET|POST /recurring/tokenization/return/{checkout_id}`

PaymentAsia subscription browser return.

- If there is no `sign`, the request is navigation only. The route reads the durable intent and renders success, failure, uncertain, or processing HTML without sending decorative/empty fields to the verifier.
- If a signed payload is present, it forwards the tokenization result to `biz-app /recurring/tokenization/record`. On success, the rendered page requires exactly one active recurring order item and an order ID.

The page uses the same visible return template and `postMessage` wake-up protocol as ordinary checkout; it does not close itself.

---

#### `POST /recurring/tokenization/notify/{checkout_id}`

Authoritative signed tokenization notification. It calls the same idempotent `biz-app /recurring/tokenization/record` endpoint used by a signed browser return.

**Success — `200`**

```json
{
  "ok": true,
  "checkout": {
    "order_id": 123,
    "status": "COMPLETE",
    "idempotent": false,
    "order_items": [ { "recurring_status": "ACTIVE" } ]
  }
}
```

---

#### `POST /recurring/payment/notify`

PaymentAsia recurring execution notification. The body may be form data or JSON. It is forwarded to `biz-app /recurring/payment/record`, which verifies and idempotently stores the execution.

**Success — `200`**

```json
{
  "ok": true,
  "recurring_payment": {
    "id": 801,
    "order_item_id": 901,
    "execution_number": 2,
    "amount": "29.90",
    "currency": "HKD",
    "status": "SUCCESS",
    "idempotent": false
  }
}
```

## 9. Checkout client protocol

### 9.1 Ordinary cart checkout

1. Fetch `GET /payment_networks` and present exactly the returned methods.
2. Re-read every cart product and inventory; do not permit a product with recurring fields in the cart.
3. Require a valid/refreshable customer token.
4. Call `POST /checkout` with product IDs, quantities, selected network, and preferably `response_mode: "json"` for a real popup launch.
5. Submit `fields` to `action_url` in the controlled payment window, or render the returned HTML.
6. Retain `checkout_id` and `checkout_reference` before gateway navigation.
7. Poll authenticated `/checkout/status/{checkout_id}` with a bounded interval.
8. Treat `PINGBIZ_ESTORE_CHECKOUT_COMPLETE` only as a trigger for an immediate status refresh.
9. Accept success only when status says `complete: true` and `status: "S"`.
10. Clear the cart only after authoritative success.
11. Keep the return page/popup visible long enough for the customer to read its result; do not close merely because a checkout ID was detected.
12. On timeout or persistent `R`, preserve cart/summary and show recovery guidance.

### 9.2 Subscription enrollment

1. Display approved recurring products separately or with a clear Subscribe action; do not add them to the ordinary cart.
2. Re-read product and inventory, then call `POST /subscribe` with one product and quantity.
3. Open/render the returned tokenization redirect HTML.
4. Retain the checkout ID from the recurring return/notify URL or HTML data.
5. Poll the same authenticated `/checkout/status/{checkout_id}` endpoint.
6. Treat `recurring_checkout_status` as progress detail, but use top-level `S`, `F`, or `U` for terminal UI handling.
7. Accept subscription success only after status `S` and an order ID; then re-read order items and require the recurring item to contain a schedule reference and `ACTIVE`/terminal recurring state.
8. Do not expect a one-time `Payment` row for subscription creation.
9. Recurring execution notifications happen server-to-server; customer UIs observe current schedule state through order items.

A suitable iframe sandbox for HTML mode remains:

```html
sandbox="allow-forms allow-scripts allow-same-origin allow-top-navigation-by-user-activation"
```

Use the narrowest sandbox that still permits the configured PaymentAsia flow. Return pages use `postMessage(..., '*')`; validate message source/window where possible and never treat message fields as payment authority.

## 10. Customer-token lifecycle expected by the reference UI

The reference implementation stores the following in `sessionStorage`:

- `ACCESS_TOKEN`
- `REFRESH_TOKEN`
- `EXPIRY`
- `REFRESH_EXPIRY`
- `USER`

It stores expiries five seconds early, refreshes through `POST /refresh` before authenticated calls, and clears the session on refresh expiry/failure. Its `AuthGuard` checks for a valid/refreshable token before protected routes.

A customized client may use an equivalent secure implementation. Native apps should use platform secure storage. A web app must never move PingBusiness merchant credentials into browser storage.

## 11. Product media convention

The reference storefront selects images by MIME type and prefers a file whose description is exactly:

```text
__PINGBIZ_MAIN_TITLE_IMAGE__
```

If none exists, it uses the first image file. Non-image files are offered as downloads. This marker is a reference-UI convention, not a separate endpoint guarantee.

## 12. Security and isolation guarantees implemented by the canonical code

- Customer bearer tokens authenticate only when introspection returns literal boolean `active: true` and a non-empty `sub`.
- Customer identity is taken from the token subject and mapped to one PingBusiness customer in the configured merchant/store.
- The merchant API key and scope identifiers remain server-side and are attached only by `estore-app`.
- Startup resolves and validates exactly one merchant/store relationship.
- Public catalog reads are constrained through the configured eStore scope and approved-product behavior in `biz-app`.
- Customer profile, order, order-item, payment, and checkout-status reads verify customer ownership and configured-store scope.
- Customer-supplied prices, totals, merchant/store/customer IDs, callback URLs, and merchant reference are not trusted.
- Ordinary checkout and subscription checkout create order-less intents; orders are created only after trusted payment or recurring-schedule acceptance.
- Intent caller data is immutable after creation, and `estore-app` never attempts a generic intent update.
- Ordinary checkout approval and recurring subscription creation are each bound to a hashed server-derived snapshot.
- One Standard checkout launch is claimed and stored by `biz-app`; identical retries do not create new launch authority.
- Payment callbacks are forwarded server-to-server for signature verification and trusted intent locking/finalization.
- Octopus totals must be exact HKD 0.10 increments and are rejected by trusted `biz-app` before signing when incompatible.
- Return-page `postMessage` events are wake-up signals only; authenticated `/checkout/status` is authoritative.
- Raw sensitive recurring tokenization material is not returned in customer-facing order-item serialization.

## 13. Client acceptance checklist

A conforming UI or mobile client must satisfy all of the following:

- Calls only the configured `estore-app` base URL.
- Contains no PingBusiness merchant API key or scope headers.
- Treats product amount/currency/cart totals as display estimates until checkout.
- Distinguishes ordinary and recurring products from the three recurring fields; uses cart checkout only for ordinary products and `/subscribe` only for one recurring product.
- Fetches `GET /payment_networks`, displays only those values, requires one selection, and never hard-codes or submits `UserDefine`.
- Requires HKD and merchant-enabled CreditCard before presenting subscription enrollment.
- Shows only products returned by the API and tolerates products becoming unavailable.
- Sums all inventory location rows and revalidates before checkout.
- Uses bearer auth only on customer-protected routes.
- Refreshes or expires tokens correctly.
- Never uses caller-supplied customer IDs to establish scope.
- Requests media as blobs and revokes object URLs.
- Handles JSON, HTML, and binary responses according to endpoint.
- Treats checkout/tokenization `postMessage` as untrusted notification only.
- Uses `response_mode: json` for robust popup launch when appropriate, retains checkout identifiers before cross-origin navigation, and does not auto-close the result window merely because an identifier exists.
- Confirms checkout through `/checkout/status` before clearing an ordinary cart.
- Re-reads subscription order items after success and does not expect a one-time Payment row for enrollment.
- Preserves a recovery path for a long-running `R` checkout.
- Does not expose unsupported order/payment mutation controls.
- Handles `400`, `401`, `403`, `404`, `409`, `500`, and `502`, plus bodyless `204` responses.
