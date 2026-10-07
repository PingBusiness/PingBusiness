import { Injectable } from '@angular/core';

import { centreSecurePopup, securePopupFeatures } from '../utils';

/**
 * Holds the hosted-payment popup across an SPA navigation.
 *
 * Browsers only allow window.open() inside a user gesture, so the cart opens the
 * (blank) secure window the moment the customer clicks Proceed to Checkout, and
 * the checkout page then takes that same window over to post the provider
 * launch into it. One click, one window — matching the Figma flow.
 */
@Injectable({ providedIn: 'root' })
export class SecurePopupService {
  private popups = new Map<string, Window>();

  /** Open a blank, centred secure window and remember it under `name`. */
  open(name: string, title = 'Preparing secure payment'): Window | null {
    this.close(name);
    let popup: Window | null = null;
    try {
      popup = window.open('', name, securePopupFeatures());
    } catch (_) {
      popup = null;
    }
    if (!popup) {
      return null;
    }
    centreSecurePopup(popup);
    try {
      const doc = popup.document;
      doc.open();
      doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title></head><body><main style="font-family:system-ui;padding:2rem"><h1>${title}...</h1><p>Please keep this window open.</p></main></body></html>`);
      doc.close();
    } catch (_) {}
    this.popups.set(name, popup);
    return popup;
  }

  /** Hand the remembered window over to the caller (and forget it here). */
  take(name: string): Window | null {
    const popup = this.popups.get(name) || null;
    this.popups.delete(name);
    return popup && !popup.closed ? popup : null;
  }

  close(name: string): void {
    const popup = this.popups.get(name);
    this.popups.delete(name);
    if (popup && !popup.closed) {
      try { popup.close(); } catch (_) {}
    }
  }
}
