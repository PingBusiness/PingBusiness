/**
 * Structured contents of the Product `details` field.
 *
 * biz-app stores `details` as a nullable free-form STRING.
 * PingBusiness uses that string as a JSON envelope for the extra product fields
 * The design needs but that have no dedicated column of their own.
 *
 * IMPORTANT: biz-ui and estore-ui MUST read and write `details` ONLY through this
 * module, and this file MUST stay byte-for-byte identical in both apps, so the two
 * sides always interpret the JSON the same way. Add new fields here (and nowhere
 * else) as the design grows — e.g. sku, isbn, category.
 *
 * Today the only such field is the marketing tagline (the short subtitle under the
 * product name). Every other design field maps to a real Product column
 * (name, description, amount, currency, recurring_*).
 */
export interface ProductDetails {
  /** Short marketing subtitle shown under the product name. */
  tagline?: string;
}

/**
 * Parse the raw `details` string into a ProductDetails object.
 *
 * Tolerant by design: a value that is not a JSON object is treated as a legacy
 * plain-text tagline (that is how `details` was used before this envelope), so
 * existing records keep rendering correctly.
 */
export function parseProductDetails(raw: string | null | undefined): ProductDetails {
  const value = (raw ?? '').trim();
  if (!value) {
    return {};
  }
  if (value.charAt(0) === '{') {
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === 'object') {
        return {
          tagline: typeof parsed.tagline === 'string' ? parsed.tagline : undefined
        };
      }
    } catch {
      // Not valid JSON — fall through to the legacy plain-text reading.
    }
  }
  return { tagline: value };
}

/**
 * Serialize ProductDetails back into the string stored in `details`.
 * Returns null when there is nothing to store, so the column stays clean.
 */
export function serializeProductDetails(details: ProductDetails): string | null {
  const clean: ProductDetails = {};
  const tagline = (details.tagline ?? '').trim();
  if (tagline) {
    clean.tagline = tagline;
  }
  return Object.keys(clean).length ? JSON.stringify(clean) : null;
}
