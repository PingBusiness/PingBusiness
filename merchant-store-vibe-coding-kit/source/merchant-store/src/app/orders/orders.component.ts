import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ORDER_STATUS_LABELS } from '../app.constants';
import { Order, OrderItem, Payment, Product, ProductFile } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage, asArray, formatMoney, isRecurringPlan, recurringPlanLabel, toCents } from '../utils';

const MAIN_TITLE_IMAGE_DESCRIPTION = '__PINGBIZ_MAIN_TITLE_IMAGE__';

@Component({
  selector: 'app-orders',
  templateUrl: './orders.component.html',
  styleUrls: ['./orders.component.css']
})
export class OrdersComponent implements OnInit, OnDestroy {
  orders: Order[] = [];
  orderItems: OrderItem[] = [];
  payments: Payment[] = [];
  statusFilter = '';
  typeFilter = '';
  loading = false;
  error = '';
  openMenuId: number | null = null;
  /** Viewport coordinates for the open row menu (fixed-positioned). */
  menuPos: { top: number; right: number } | null = null;
  detailOrder: Order | null = null;
  private productNames = new Map<number, string>();
  private products = new Map<number, Product>();
  private detailImages = new Map<number, string>();
  private detailImageUrls: string[] = [];

  constructor(private api: EstoreApiService, private toast: ToastService) {}

  ngOnInit(): void { this.load(); }

  ngOnDestroy(): void { this.revokeDetailImages(); }

  toggleMenu(orderId: number | undefined, event: MouseEvent): void {
    event.stopPropagation();
    if (this.openMenuId === orderId) {
      this.closeMenu();
      return;
    }
    this.openMenuId = orderId ?? null;
    // Anchor the fixed menu to the trigger button in viewport coordinates.
    const button = event.currentTarget as HTMLElement | null;
    if (button) {
      const rect = button.getBoundingClientRect();
      this.menuPos = { top: rect.bottom + 4, right: window.innerWidth - rect.right };
    }
  }

  // Close on any outside click, and on scroll/resize (the fixed menu would
  // otherwise detach from its button).
  @HostListener('document:click')
  @HostListener('window:scroll')
  @HostListener('window:resize')
  closeMenu(): void {
    this.openMenuId = null;
    this.menuPos = null;
  }

  load(): void {
    this.loading = true;
    this.error = '';
    forkJoin({
      orders: this.api.getOrders().pipe(catchError(err => { this.toast.show(apiErrorMessage(err), 'error'); return of([]); })),
      items: this.api.getOrderItems().pipe(catchError(() => of([]))),
      payments: this.api.getPayments().pipe(catchError(() => of([]))),
      products: this.api.getProducts().pipe(catchError(() => of([])))
    }).subscribe(({ orders, items, payments, products }) => {
      this.orders = asArray<Order>(orders).sort((a, b) => {
        const difference = this.orderTimestamp(b.created_at) - this.orderTimestamp(a.created_at);
        return difference !== 0 ? difference : Number(b.id || 0) - Number(a.id || 0);
      });
      this.orderItems = asArray<OrderItem>(items);
      this.payments = asArray<Payment>(payments);
      this.productNames.clear();
      this.products.clear();
      asArray<Product>(products).forEach(product => {
        if (product.id) {
          const id = Number(product.id);
          this.productNames.set(id, product.name || `Product #${id}`);
          this.products.set(id, product);
        }
      });
      this.loading = false;
    });
  }

  // --- Order Details modal (read-only, presentation only) ---
  openDetail(order: Order, event: Event): void {
    event.stopPropagation();
    this.openMenuId = null;
    this.menuPos = null;
    this.detailOrder = order;
    this.loadDetailImages(order);
  }

  closeDetail(): void {
    this.detailOrder = null;
    this.revokeDetailImages();
  }

  detailItems(): OrderItem[] {
    return this.detailOrder ? this.orderItemsFor(this.detailOrder) : [];
  }

  productName(item: OrderItem): string {
    return this.productNames.get(Number(item.product_id)) || `Product #${item.product_id}`;
  }

  itemPlanLabel(item: OrderItem): string {
    return isRecurringPlan(item) ? recurringPlanLabel(item) : 'One-time payment';
  }

  itemPrice(item: OrderItem): string {
    return formatMoney(item.amount, this.detailOrder?.currency);
  }

  detailImage(item: OrderItem): string | undefined {
    return item.id != null ? this.detailImages.get(Number(item.id)) : undefined;
  }

  private loadDetailImages(order: Order): void {
    this.revokeDetailImages();
    this.orderItemsFor(order).forEach(item => {
      const product = this.products.get(Number(item.product_id));
      if (!product || item.id == null) { return; }
      const imageFiles = asArray<ProductFile>(product.files)
        .filter(file => String(file.mime_type || '').toLowerCase().startsWith('image/'));
      const mainImage = imageFiles.find(file => file.description === MAIN_TITLE_IMAGE_DESCRIPTION) || imageFiles[0];
      if (!mainImage?.id) { return; }
      const itemId = Number(item.id);
      this.api.getProductImage(mainImage.id).pipe(catchError(() => of(undefined))).subscribe(blob => {
        if (!blob) { return; }
        const url = URL.createObjectURL(blob);
        this.detailImageUrls.push(url);
        this.detailImages.set(itemId, url);
      });
    });
  }

  private revokeDetailImages(): void {
    this.detailImageUrls.forEach(url => URL.revokeObjectURL(url));
    this.detailImageUrls = [];
    this.detailImages.clear();
  }

  productsLabel(order: Order): string {
    const items = this.orderItemsFor(order);
    if (!items.length) {
      return '—';
    }
    return items
      .map(item => this.productNames.get(Number(item.product_id)) || `Product #${item.product_id}`)
      .join(', ');
  }

  private orderTimestamp(value?: string): number {
    if (!value) { return 0; }
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) ? timestamp : 0;
  }

  filteredOrders(): Order[] {
    return this.orders.filter(order => {
      if (this.statusFilter && order.status !== this.statusFilter) { return false; }
      return !this.typeFilter || this.orderKind(order) === this.typeFilter;
    });
  }

  orderItemsFor(order: Order): OrderItem[] {
    return this.orderItems.filter(item => item.order_id === order.id);
  }

  orderKind(order: Order): 'one_time' | 'subscription' {
    return this.orderItemsFor(order).some(item => isRecurringPlan(item)) ? 'subscription' : 'one_time';
  }

  orderKindLabel(order: Order): string {
    return this.orderKind(order) === 'subscription' ? 'Subscription' : 'One-time';
  }

  itemCount(order: Order): number {
    return this.orderItemsFor(order).reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  }

  paymentCount(order: Order): number {
    return this.payments.filter(payment => payment.order_id === order.id).length;
  }

  /**
   * The card network for an order — biz-app has no per-order method column.
   *
   * One-time orders: it comes from a payment's `details` JSON (`payment_network`).
   * Prefers a SUCCESS record; falls back to any payment carrying a network.
   *
   * Subscriptions: there is no per-order gateway record (the charges live in the
   * recurring table, which the storefront API does not expose), so they always
   * bill on CreditCard via PaymentAsia recurring — mirror the merchant portal.
   */
  paymentMethod(order: Order): string {
    if (this.orderKind(order) === 'subscription') {
      return 'CreditCard';
    }
    const parse = (payment: Payment): Record<string, any> | null => {
      if (!payment.details) {
        return null;
      }
      try {
        const parsed = JSON.parse(payment.details);
        return parsed && typeof parsed === 'object' ? parsed : null;
      } catch {
        return null;
      }
    };
    const parsed = this.payments
      .filter(payment => payment.order_id === order.id)
      .map(parse)
      .filter((details): details is Record<string, any> => !!details && !!details['payment_network']);
    const success = parsed.find(details =>
      String(details['paymentasia_status_normalized'] || '').toUpperCase() === 'SUCCESS');
    return String((success || parsed[0])?.['payment_network'] || '—');
  }

  statusLabel(status?: string): string {
    return status ? (ORDER_STATUS_LABELS[status] || status) : 'Unknown';
  }

  recordedAmount(order: Order): string { return formatMoney(order.total_amount, order.currency); }

  plannedCommitment(order: Order): string {
    // Sum in integer cents (price × executions), convert once — no float drift.
    const cents = this.orderItemsFor(order).reduce((total, item) => {
      const executions = Math.max(1, Number(item.recurring_total_execution_times) || 1);
      return total + toCents(item.amount) * executions;
    }, 0);
    return formatMoney(cents / 100, order.currency);
  }

  primaryAmount(order: Order): string {
    return this.orderKind(order) === 'one_time' ? this.recordedAmount(order) : this.plannedCommitment(order);
  }
}
