import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { CheckoutStatus, Inventory, Product, SubscribePayload } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { KeycloakService } from '../services/keycloak.service';
import {
  apiErrorMessage,
  asArray,
  formatIsoDate,
  formatMoney,
  isRecurringPlan,
  nextHongKongCalendarDate,
  recurringPlanLabel,
  recurringPlannedTotal,
  toNumber
} from '../utils';

@Component({
  selector: 'app-subscription-checkout',
  templateUrl: './subscription-checkout.component.html',
  styleUrls: ['./subscription-checkout.component.css']
})
export class SubscriptionCheckoutComponent implements OnInit, OnDestroy {
  @ViewChild('checkoutFrame') checkoutFrame?: ElementRef<HTMLIFrameElement>;

  product?: Product;
  quantity = 1;
  available = 0;
  loadingProduct = true;
  starting = false;
  checkoutStarted = false;
  completed = false;
  checkoutFrameUrl: SafeResourceUrl | null = null;
  externalCheckoutUrl = '';
  recurringCheckoutStatus = '';
  orderId?: number;
  paymentReference = '';
  error = '';
  notice = '';

  private checkoutFrameObjectUrl = '';
  private checkoutId = '';
  private checkoutPopup: Window | null = null;
  private statusPollHandle: any = null;
  private statusPollAttempts = 0;
  private checkoutStatusInFlight = false;
  private readonly messageHandler = (event: MessageEvent) => this.onCheckoutMessage(event);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: EstoreApiService,
    private keycloak: KeycloakService,
    private sanitizer: DomSanitizer
  ) {}

  ngOnInit(): void {
    window.addEventListener('message', this.messageHandler);
    const productId = Number(this.route.snapshot.paramMap.get('id'));
    this.quantity = Math.max(1, Math.trunc(Number(this.route.snapshot.queryParamMap.get('quantity')) || 1));
    if (!productId) {
      this.loadingProduct = false;
      this.error = 'Subscription product id is missing.';
      return;
    }

    forkJoin({
      product: this.api.getProduct(productId),
      inventories: this.api.getInventories(productId),
      paymentNetworks: this.api.getPaymentNetworks()
    }).pipe(catchError(err => {
      this.error = apiErrorMessage(err);
      return of(undefined);
    })).subscribe(result => {
      this.loadingProduct = false;
      if (!result) {
        return;
      }
      if (result.product.state !== 'A') {
        this.error = 'This subscription product is no longer available.';
        return;
      }
      if (!isRecurringPlan(result.product)) {
        this.error = 'This is a one-time product. Add it to the cart instead.';
        return;
      }
      if (String(result.product.currency || '').toUpperCase() !== 'HKD') {
        this.error = 'Subscriptions currently require HKD.';
        return;
      }
      if (!asArray<string>(result.paymentNetworks?.payment_networks).includes('CreditCard')) {
        this.error = 'Credit Card is not enabled for this merchant, so subscription checkout cannot start.';
        return;
      }
      this.product = result.product;
      this.available = asArray<Inventory>(result.inventories).reduce((sum, row) => sum + toNumber(row?.quantity), 0);
      if (this.quantity > this.available) {
        this.quantity = Math.max(1, this.available);
      }
    });
  }

  ngOnDestroy(): void {
    window.removeEventListener('message', this.messageHandler);
    this.stopStatusPolling();
    this.clearCheckoutFrame();
  }

  planLabel(): string {
    return recurringPlanLabel(this.product);
  }

  firstChargeDate(): string {
    return formatIsoDate(nextHongKongCalendarDate());
  }

  amountPerPayment(): string {
    return formatMoney(toNumber(this.product?.amount) * Math.max(1, Math.trunc(Number(this.quantity) || 1)), this.product?.currency);
  }

  plannedCommitment(): string {
    return formatMoney(
      recurringPlannedTotal(this.product?.amount, this.product, this.quantity),
      this.product?.currency
    );
  }

  quantityExceedsStock(): boolean {
    return Math.max(1, Math.trunc(Number(this.quantity) || 1)) > this.available;
  }

  startSubscription(): void {
    if (!this.product?.id || this.starting || this.completed) {
      return;
    }
    this.error = '';
    this.notice = '';
    const quantity = Math.max(1, Math.trunc(Number(this.quantity) || 1));
    if (quantity > this.available) {
      this.error = 'The requested quantity is unavailable.';
      return;
    }
    if (!isRecurringPlan(this.product)) {
      this.error = 'This product is not a subscription.';
      return;
    }

    this.quantity = quantity;
    this.starting = true;
    this.checkoutStarted = true;
    this.recurringCheckoutStatus = 'TOKENIZATION_REQUESTING';
    this.stopStatusPolling();
    this.clearCheckoutFrame();
    this.externalCheckoutUrl = '';
    this.preparePopup();

    this.keycloak.getValidAccessToken().subscribe({
      next: token => {
        if (!token) {
          this.starting = false;
          this.checkoutStarted = false;
          this.closeEmptyPopup();
          this.router.navigate(['/signin'], {
            queryParams: { returnUrl: `/subscribe/${this.product?.id}?quantity=${this.quantity}` }
          });
          return;
        }
        const payload: SubscribePayload = {
          product_id: Number(this.product?.id),
          quantity: this.quantity
        };
        this.api.subscribe(payload).subscribe({
          next: html => {
            this.starting = false;
            this.checkoutId = this.extractCheckoutId(html);
            this.externalCheckoutUrl = this.extractExternalCheckoutUrl(html);
            if (this.checkoutPopup && !this.checkoutPopup.closed && this.externalCheckoutUrl) {
              this.checkoutPopup.location.href = this.externalCheckoutUrl;
              this.notice = 'Complete secure card verification in the PaymentAsia window.';
            } else {
              this.closeEmptyPopup();
              this.notice = 'Complete secure card verification below.';
              this.setCheckoutFrame(html);
            }
            if (!this.checkoutId) {
              this.error = 'Subscription checkout started, but its tracking identifier could not be read. Keep the secure checkout open and refresh Subscriptions later.';
            } else {
              this.startStatusPolling();
              this.refreshCheckoutStatus(false);
            }
          },
          error: err => {
            this.starting = false;
            this.checkoutStarted = false;
            this.error = apiErrorMessage(err);
            this.closeEmptyPopup();
            this.clearCheckoutFrame();
          }
        });
      },
      error: err => {
        this.starting = false;
        this.checkoutStarted = false;
        this.error = apiErrorMessage(err);
        this.closeEmptyPopup();
      }
    });
  }

  recurringStatusLabel(): string {
    const labels: Record<string, string> = {
      TOKENIZATION_REQUESTING: 'Requesting secure card verification',
      TOKENIZATION_PENDING: 'Waiting for card verification',
      TOKENIZATION_FAILED: 'Card verification failed',
      TOKENIZATION_ERROR: 'Card verification could not start',
      TOKENIZATION_UNKNOWN: 'Card verification result is uncertain',
      SCHEDULE_CREATING: 'Creating the subscription schedule',
      SCHEDULE_CREATION_FAILED: 'Subscription setup failed',
      SCHEDULE_CREATION_UNKNOWN: 'Subscription setup result is uncertain',
      COMPLETE: 'Subscription complete',
      LOCAL_FINALIZATION_FAILED: 'Local subscription finalization failed',
      COMPENSATION_REQUIRED: 'Manual reconciliation required'
    };
    return labels[this.recurringCheckoutStatus] || this.recurringCheckoutStatus || 'Preparing subscription';
  }

  currentStageIndex(): number {
    if (this.completed) {
      return 3;
    }
    if (this.recurringCheckoutStatus === 'SCHEDULE_CREATING' || this.recurringCheckoutStatus === 'COMPLETE') {
      return 2;
    }
    return 1;
  }

  secureWindowOpen(): boolean {
    return !!this.checkoutPopup && !this.checkoutPopup.closed;
  }

  reopenSecureWindow(): void {
    if (!this.externalCheckoutUrl) {
      return;
    }
    this.checkoutPopup = window.open(
      this.externalCheckoutUrl,
      'pingbizSubscriptionCheckout',
      'width=760,height=760,resizable=yes,scrollbars=yes'
    );
    if (!this.checkoutPopup) {
      this.error = 'Your browser blocked the secure checkout window. Allow pop-ups or continue in the embedded checkout below.';
    }
  }

  private preparePopup(): void {
    this.checkoutPopup = window.open('', 'pingbizSubscriptionCheckout', 'width=760,height=760,resizable=yes,scrollbars=yes');
    if (!this.checkoutPopup) {
      this.notice = 'Your browser blocked the secure checkout window. The checkout will open below instead.';
      return;
    }
    try {
      this.checkoutPopup.document.title = 'Preparing secure subscription checkout';
      this.checkoutPopup.document.body.innerHTML = '<main style="font-family:system-ui;padding:2rem"><h1>Preparing secure card verification...</h1><p>Please keep this window open.</p></main>';
    } catch (_) {}
  }

  private setCheckoutFrame(html: string): void {
    this.clearCheckoutFrame();
    const blob = new Blob([html], { type: 'text/html' });
    this.checkoutFrameObjectUrl = URL.createObjectURL(blob);
    this.checkoutFrameUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.checkoutFrameObjectUrl);
  }

  private clearCheckoutFrame(): void {
    if (this.checkoutFrameObjectUrl) {
      URL.revokeObjectURL(this.checkoutFrameObjectUrl);
      this.checkoutFrameObjectUrl = '';
    }
    this.checkoutFrameUrl = null;
  }

  private extractCheckoutId(html: string): string {
    try {
      const document = new DOMParser().parseFromString(html, 'text/html');
      const bodyId = document.body?.getAttribute('data-checkout-id') || '';
      if (bodyId) {
        return decodeURIComponent(bodyId);
      }
    } catch (_) {}
    const fallback = html.match(/data-checkout-id=["']([^"']+)["']/i);
    return fallback?.[1] ? decodeURIComponent(fallback[1]) : '';
  }

  private extractExternalCheckoutUrl(html: string): string {
    try {
      const document = new DOMParser().parseFromString(html, 'text/html');
      const href = (document.querySelector('a[href]') as HTMLAnchorElement | null)?.href || '';
      const parsed = new URL(href);
      return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : '';
    } catch (_) {
      return '';
    }
  }

  private onCheckoutMessage(event: MessageEvent): void {
    const data = event.data || {};
    if (!data || data.type !== 'PINGBIZ_ESTORE_CHECKOUT_COMPLETE') {
      return;
    }
    const frameWindow = this.checkoutFrame?.nativeElement?.contentWindow;
    const popupWindow = this.checkoutPopup;
    if (event.source && event.source !== frameWindow && event.source !== popupWindow) {
      return;
    }
    const messageCheckoutId = data.checkoutId || data.checkout_id || '';
    if (messageCheckoutId && this.checkoutId && messageCheckoutId !== this.checkoutId) {
      return;
    }
    if (!this.checkoutId && messageCheckoutId) {
      this.checkoutId = String(messageCheckoutId);
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
        this.notice = 'Subscription setup is still awaiting a final result. Refresh Subscriptions later.';
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
        this.recurringCheckoutStatus = String(status?.recurring_checkout_status || '');
        this.updateProgressNotice(fromReturnMessage);
        const terminal = status?.status === 'S' || status?.status === 'F' || status?.status === 'U';
        if (status?.complete === true && terminal) {
          this.finishSubscription({
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

  private updateProgressNotice(fromReturnMessage: boolean): void {
    if (this.recurringCheckoutStatus === 'SCHEDULE_CREATING') {
      this.notice = 'Card verified. Creating your subscription schedule...';
    } else if (this.recurringCheckoutStatus === 'TOKENIZATION_PENDING') {
      this.notice = 'Waiting for secure card verification...';
    } else if (this.recurringCheckoutStatus === 'COMPLETE') {
      this.notice = 'Subscription schedule accepted. Confirming the order...';
    } else if (fromReturnMessage) {
      this.notice = 'Card-verification response received. Confirming subscription status...';
    }
  }

  private finishSubscription(data: any): void {
    const success = data.success === true || data.success === 'true';
    this.stopStatusPolling();
    this.starting = false;
    this.completed = true;
    this.orderId = Number(data.orderId || data.order_id) || undefined;
    this.paymentReference = data.paymentReference || data.payment_reference || '';
    if (success) {
      this.error = '';
      this.notice = 'Subscription created successfully. The first scheduled payment is on the next Hong Kong calendar day.';
      // Keep the PaymentAsia window open so its return URL can display the final success message.
    } else {
      this.notice = '';
      const detail = this.recurringCheckoutStatus ? ` (${this.recurringStatusLabel()})` : '';
      this.error = `Subscription checkout finished, but it was not successful${detail}.`;
    }
  }

  private stopStatusPolling(): void {
    if (this.statusPollHandle) {
      window.clearInterval(this.statusPollHandle);
      this.statusPollHandle = null;
    }
  }

  private closeEmptyPopup(): void {
    if (this.checkoutPopup && !this.checkoutPopup.closed) {
      try { this.checkoutPopup.close(); } catch (_) {}
    }
    this.checkoutPopup = null;
  }
}
