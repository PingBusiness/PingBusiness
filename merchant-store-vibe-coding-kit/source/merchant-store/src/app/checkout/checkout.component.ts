import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { forkJoin, of, Subscription } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { CartLine, CheckoutLaunch, CheckoutPayload, CheckoutStatus, Inventory, Product } from '../app.types';
import { CartService } from '../services/cart.service';
import { EstoreApiService } from '../services/estore-api.service';
import { KeycloakService } from '../services/keycloak.service';
import { apiErrorMessage, asArray, formatMoney, isRecurringPlan, toNumber } from '../utils';

@Component({
  selector: 'app-checkout',
  templateUrl: './checkout.component.html',
  styleUrls: ['./checkout.component.css']
})
export class CheckoutComponent implements OnInit, OnDestroy {
  items: CartLine[] = [];
  summaryItems: CartLine[] = [];
  checkoutStarted = false;
  secureCheckoutReady = false;
  loading = false;
  completed = false;
  orderId?: number;
  checkoutReference = '';
  paymentReference = '';
  paymentNetworks: string[] = [];
  selectedNetwork = '';
  networksLoading = true;
  error = '';
  notice = '';

  private cartSub?: Subscription;
  private checkoutPopup: Window | null = null;
  private checkoutLaunch?: CheckoutLaunch;
  private checkoutId = '';
  private statusPollHandle: any = null;
  private statusPollAttempts = 0;
  private checkoutStatusInFlight = false;
  private readonly messageHandler = (event: MessageEvent) => this.onCheckoutMessage(event);

  constructor(
    private cart: CartService,
    private api: EstoreApiService,
    private keycloak: KeycloakService,
    private router: Router
  ) {}

  ngOnInit(): void {
    window.addEventListener('message', this.messageHandler);
    this.loadPaymentNetworks();
    this.cartSub = this.cart.items$.subscribe(items => {
      this.items = items;
      if (!this.checkoutStarted && !this.completed) {
        this.summaryItems = [...items];
      }
    });
  }

  ngOnDestroy(): void {
    window.removeEventListener('message', this.messageHandler);
    this.cartSub?.unsubscribe();
    this.stopStatusPolling();
    this.clearSecureCheckout();
    this.closeCheckoutPopup();
  }

  currency(): string {
    return String(this.summaryItems[0]?.product.currency || '');
  }

  subtotal(): string {
    return formatMoney(this.cart.subtotal(this.summaryItems), this.currency());
  }

  lineTotal(item: CartLine): string {
    return formatMoney(this.cart.lineTotal(item), item.product.currency);
  }

  paymentNetworkLabel(network: string): string {
    return ({ Wechat: 'WeChat Pay', CreditCard: 'Credit Card', Fps: 'FPS' } as Record<string, string>)[network] || network;
  }

  secureWindowOpen(): boolean {
    return !!this.checkoutPopup && !this.checkoutPopup.closed;
  }

  reopenSecureWindow(): void {
    if (this.checkoutPopup && !this.checkoutPopup.closed) {
      try { this.checkoutPopup.focus(); } catch (_) {}
      this.notice = 'The secure PaymentAsia window is open.';
      return;
    }
    if (!this.checkoutLaunch) {
      return;
    }
    const popup = window.open(
      '',
      'pingbizCartCheckout',
      'width=760,height=760,resizable=yes,scrollbars=yes'
    );
    if (!popup) {
      this.error = 'Your browser blocked the secure payment window. Allow pop-ups for this site, then try again.';
      return;
    }
    this.checkoutPopup = popup;
    this.error = '';
    if (this.submitLaunchToPopup(this.checkoutLaunch)) {
      this.notice = 'Complete payment in the secure PaymentAsia window.';
    }
  }

  submit(): void {
    if (this.loading || this.completed) {
      return;
    }
    const checkoutItems = this.items.length > 0 ? [...this.items] : [...this.summaryItems];
    this.error = '';
    this.notice = '';

    if (!this.selectedNetwork || !this.paymentNetworks.includes(this.selectedNetwork)) {
      this.error = 'Choose an available payment method before continuing.';
      return;
    }
    if (checkoutItems.length === 0) {
      this.checkoutStarted = false;
      this.error = 'Your cart is empty.';
      return;
    }
    if (checkoutItems.some(item => isRecurringPlan(item.product))) {
      this.checkoutStarted = false;
      this.error = 'Subscriptions cannot be checked out from the cart. Use Subscribe Now on the subscription product.';
      return;
    }

    const currencies = new Set(checkoutItems.map(item => String(item.product.currency || '').toUpperCase()));
    if (currencies.size !== 1 || currencies.has('')) {
      this.error = 'All cart items must use the same currency.';
      return;
    }

    this.summaryItems = checkoutItems;
    this.checkoutStarted = true;
    this.loading = true;
    this.completed = false;
    this.orderId = undefined;
    this.checkoutId = '';
    this.checkoutReference = '';
    this.paymentReference = '';
    this.stopStatusPolling();
    this.clearSecureCheckout();
    this.preparePopup();

    this.validateCheckoutInventory(checkoutItems).subscribe({
      next: inventoryError => {
        if (inventoryError) {
          this.loading = false;
          this.checkoutStarted = false;
          this.error = inventoryError;
          this.closeEmptyPopup();
          return;
        }
        this.startCheckout(checkoutItems);
      },
      error: err => {
        this.loading = false;
        this.checkoutStarted = false;
        this.error = apiErrorMessage(err);
        this.closeEmptyPopup();
      }
    });
  }

  private loadPaymentNetworks(): void {
    this.networksLoading = true;
    this.api.getPaymentNetworks().subscribe({
      next: response => {
        this.networksLoading = false;
        this.paymentNetworks = Array.isArray(response?.payment_networks) ? response.payment_networks : [];
        this.selectedNetwork = this.paymentNetworks.length === 1 ? this.paymentNetworks[0] : '';
        if (this.paymentNetworks.length === 0) {
          this.error = 'No payment methods are currently available for this merchant.';
        }
      },
      error: err => {
        this.networksLoading = false;
        this.paymentNetworks = [];
        this.selectedNetwork = '';
        this.error = apiErrorMessage(err);
      }
    });
  }

  private startCheckout(checkoutItems: CartLine[]): void {
    this.keycloak.getValidAccessToken().subscribe({
      next: token => {
        if (!token) {
          this.loading = false;
          this.checkoutStarted = false;
          this.closeEmptyPopup();
          this.router.navigate(['/signin'], { queryParams: { returnUrl: '/checkout' } });
          return;
        }
        this.api.checkout(this.payload(checkoutItems)).subscribe({
          next: launch => {
            this.loading = false;
            if (!this.isValidCheckoutLaunch(launch)) {
              this.checkoutStarted = false;
              this.error = 'The checkout service returned an invalid secure-payment launch response.';
              this.closeEmptyPopup();
              this.clearSecureCheckout();
              return;
            }

            this.checkoutLaunch = launch;
            this.checkoutId = String(launch.checkout_id);
            this.checkoutReference = String(launch.checkout_reference);
            this.paymentReference = this.checkoutReference;
            this.secureCheckoutReady = true;

            const launched = this.submitLaunchToPopup(launch);
            this.notice = launched
              ? 'Complete payment in the secure PaymentAsia window.'
              : 'Your browser blocked the secure payment window. Use Open secure payment to continue.';

            this.startStatusPolling();
            this.refreshCheckoutStatus(false);
          },
          error: err => {
            this.loading = false;
            this.checkoutStarted = false;
            this.error = apiErrorMessage(err);
            this.closeEmptyPopup();
            this.clearSecureCheckout();
          }
        });
      },
      error: err => {
        this.loading = false;
        this.checkoutStarted = false;
        this.error = apiErrorMessage(err);
        this.closeEmptyPopup();
      }
    });
  }

  private validateCheckoutInventory(items: CartLine[]) {
    const checks = items.map(item => forkJoin({
      product: this.api.getProduct(item.product_id),
      inventories: this.api.getInventories(item.product_id)
    }).pipe(
      map(result => {
        const available = asArray<Inventory>(result.inventories).reduce((sum, row) => sum + toNumber(row?.quantity), 0);
        return { item, product: result.product, available, error: '', unavailable: false };
      }),
      catchError(err => of({
        item,
        product: undefined as Product | undefined,
        available: 0,
        error: apiErrorMessage(err),
        unavailable: err?.status === 403 || err?.status === 404
      }))
    ));

    return forkJoin(checks).pipe(map(results => {
      const unavailable = results.find(result => result.unavailable || (result.product && result.product.state !== 'A'));
      if (unavailable) {
        const name = unavailable.item.product?.name || `product ${unavailable.item.product_id}`;
        this.cart.remove(unavailable.item.product_id);
        return `${name} is no longer available and was removed from your cart.`;
      }
      const recurring = results.find(result => result.product && isRecurringPlan(result.product));
      if (recurring) {
        this.cart.remove(recurring.item.product_id);
        return `${recurring.product?.name || 'A subscription'} cannot be checked out from the cart. Use Subscribe Now instead.`;
      }
      const catalogueReadError = results.find(result => result.error);
      if (catalogueReadError) {
        return catalogueReadError.error || 'Could not refresh the product catalogue. Please try again.';
      }
      results.forEach(result => {
        if (result.product) {
          result.item.product = result.product;
          this.cart.setProduct(result.product);
        }
      });
      const insufficient = results.find(result => result.item.quantity > result.available);
      if (!insufficient) {
        return '';
      }
      const name = insufficient.item.product?.name || `product ${insufficient.item.product_id}`;
      return `${name} is unavailable in the requested quantity. Please update your cart before checkout.`;
    }));
  }

  private payload(items: CartLine[]): CheckoutPayload {
    return {
      cart: items.map(item => ({ product_id: item.product_id, quantity: item.quantity })),
      network: this.selectedNetwork,
      customer_state: 'HK',
      customer_country: 'HK',
      customer_postal_code: '000000',
      response_mode: 'json'
    };
  }

  private preparePopup(): void {
    this.closeCheckoutPopup();
    this.checkoutPopup = window.open(
      '',
      'pingbizCartCheckout',
      'width=760,height=760,resizable=yes,scrollbars=yes'
    );
    if (!this.checkoutPopup) {
      this.notice = 'Your browser blocked the secure payment window. A manual Open secure payment button will be available.';
      return;
    }
    this.writePreparingPage(this.checkoutPopup);
  }

  private writePreparingPage(popup: Window): void {
    try {
      const doc = popup.document;
      doc.open();
      doc.write('<!doctype html><html><head><meta charset="utf-8"><title>Preparing secure payment</title></head><body><main style="font-family:system-ui;padding:2rem"><h1>Preparing secure payment...</h1><p>Please keep this window open.</p></main></body></html>');
      doc.close();
    } catch (_) {}
  }

  private isValidCheckoutLaunch(value: any): value is CheckoutLaunch {
    if (!value || typeof value !== 'object') {
      return false;
    }
    const checkoutId = String(value.checkout_id || '').trim();
    const checkoutReference = String(value.checkout_reference || '').trim();
    if (!checkoutId || !checkoutReference || !value.fields || typeof value.fields !== 'object') {
      return false;
    }
    try {
      const action = new URL(String(value.action_url || ''));
      return action.protocol === 'https:' || action.protocol === 'http:';
    } catch (_) {
      return false;
    }
  }

  private submitLaunchToPopup(launch: CheckoutLaunch): boolean {
    const popup = this.checkoutPopup;
    if (!popup || popup.closed) {
      this.checkoutPopup = null;
      return false;
    }

    try {
      const action = new URL(launch.action_url);
      if (action.protocol !== 'https:' && action.protocol !== 'http:') {
        throw new Error('Unsupported checkout URL protocol');
      }

      const doc = popup.document;
      doc.open();
      doc.write('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Opening secure payment</title></head><body><main style="font-family:system-ui;padding:2rem"><h1>Opening secure payment...</h1><p>You are being transferred to PaymentAsia.</p></main></body></html>');
      doc.close();

      const form = doc.createElement('form');
      form.method = 'POST';
      form.action = action.toString();
      form.acceptCharset = 'utf-8';
      Object.entries(launch.fields || {}).forEach(([name, value]) => {
        const input = doc.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = value === undefined || value === null ? '' : String(value);
        form.appendChild(input);
      });
      doc.body.appendChild(form);
      popup.focus();
      form.submit();
      return true;
    } catch (err) {
      console.error('Could not open secure PaymentAsia checkout', err);
      this.error = 'The secure payment window could not be opened. Please try again.';
      this.closeCheckoutPopup();
      return false;
    }
  }

  private clearSecureCheckout(): void {
    this.checkoutLaunch = undefined;
    this.secureCheckoutReady = false;
  }

  private onCheckoutMessage(event: MessageEvent): void {
    const data = event.data || {};
    if (!data || data.type !== 'PINGBIZ_ESTORE_CHECKOUT_COMPLETE') {
      return;
    }
    const popupWindow = this.checkoutPopup;
    if (event.source && event.source !== popupWindow) {
      return;
    }
    const messageCheckoutId = data.checkoutId || data.checkout_id || '';
    if (messageCheckoutId && this.checkoutId && messageCheckoutId !== this.checkoutId) {
      return;
    }
    if (!this.checkoutId && messageCheckoutId) {
      this.checkoutId = String(messageCheckoutId);
      this.startStatusPolling();
    }
    const messagePaymentReference = data.paymentReference || data.payment_reference || '';
    if (messagePaymentReference) {
      this.paymentReference = String(messagePaymentReference);
    }
    this.refreshCheckoutStatus(true);
  }

  private startStatusPolling(): void {
    this.stopStatusPolling();
    if (!this.checkoutId) {
      return;
    }
    this.statusPollAttempts = 0;
    this.statusPollHandle = window.setInterval(() => {
      if (this.completed) {
        this.stopStatusPolling();
        return;
      }
      this.statusPollAttempts += 1;
      if (this.statusPollAttempts > 300) {
        this.stopStatusPolling();
        this.notice = 'Payment is still awaiting a final result. Keep your reference and refresh Orders later.';
        return;
      }
      this.refreshCheckoutStatus(false);
    }, 3000);
  }

  private refreshCheckoutStatus(fromReturnMessage: boolean): void {
    if (!this.checkoutId || this.completed || this.checkoutStatusInFlight) {
      return;
    }
    this.checkoutStatusInFlight = true;
    this.api.checkoutStatus(this.checkoutId).subscribe({
      next: (status: CheckoutStatus) => {
        this.checkoutStatusInFlight = false;
        if (status?.checkout_reference) {
          this.checkoutReference = String(status.checkout_reference);
        }
        if (status?.payment_reference) {
          this.paymentReference = String(status.payment_reference);
        }
        if (fromReturnMessage) {
          this.notice = 'Payment response received. Confirming final payment status...';
        }
        const terminal = status?.status === 'S' || status?.status === 'F' || status?.status === 'U';
        if (status?.complete === true && terminal) {
          this.finishCheckout({
            success: status.success === true || status.status === 'S',
            orderId: status.order_id,
            paymentReference: status.payment_reference
          });
        }
      },
      error: () => {
        this.checkoutStatusInFlight = false;
      }
    });
  }

  private stopStatusPolling(): void {
    if (this.statusPollHandle) {
      window.clearInterval(this.statusPollHandle);
      this.statusPollHandle = null;
    }
  }

  private finishCheckout(data: any): void {
    const success = data.success === true || data.success === 'true';
    this.stopStatusPolling();
    this.loading = false;
    this.completed = true;
    this.orderId = Number(data.orderId || data.order_id) || undefined;
    this.paymentReference = data.paymentReference || data.payment_reference || this.paymentReference || this.checkoutReference;
    if (success) {
      this.error = '';
      this.notice = 'Payment completed successfully.';
      this.cart.clear();
    } else {
      this.notice = '';
      this.error = 'Checkout finished, but the payment was not successful.';
    }
  }

  private closeEmptyPopup(): void {
    if (!this.secureCheckoutReady) {
      this.closeCheckoutPopup();
    }
  }

  private closeCheckoutPopup(): void {
    if (this.checkoutPopup && !this.checkoutPopup.closed) {
      try { this.checkoutPopup.close(); } catch (_) {}
    }
    this.checkoutPopup = null;
  }
}
