import { Component, HostListener, OnInit } from '@angular/core';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { Order, OrderItem, Product } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { ToastService } from '../services/toast.service';
import {
  apiErrorMessage,
  asArray,
  formatIsoDate,
  formatMoney,
  isRecurringPlan
} from '../utils';

@Component({
  selector: 'app-subscriptions',
  templateUrl: './subscriptions.component.html',
  styleUrls: ['./subscriptions.component.css']
})
export class SubscriptionsComponent implements OnInit {
  subscriptions: OrderItem[] = [];
  orders: Order[] = [];
  statusFilter = '';
  loading = false;
  error = '';
  openMenuId: number | null = null;
  /** Viewport coordinates for the open row menu (fixed-positioned). */
  menuPos: { top: number; right: number } | null = null;
  private productNames = new Map<number, string>();

  constructor(private api: EstoreApiService, private toast: ToastService) {}

  ngOnInit(): void {
    this.load();
  }

  toggleMenu(itemId: number | undefined, event: MouseEvent): void {
    event.stopPropagation();
    if (this.openMenuId === itemId) {
      this.closeMenu();
      return;
    }
    this.openMenuId = itemId ?? null;
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
      items: this.api.getOrderItems().pipe(catchError(err => {
        this.toast.show(apiErrorMessage(err), 'error');
        return of([]);
      })),
      orders: this.api.getOrders().pipe(catchError(() => of([]))),
      products: this.api.getProducts().pipe(catchError(() => of([])))
    }).subscribe(({ items, orders, products }) => {
      this.subscriptions = asArray<OrderItem>(items)
        .filter(item => isRecurringPlan(item))
        .sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
      this.orders = asArray<Order>(orders);
      this.productNames.clear();
      asArray<Product>(products).forEach(product => {
        if (product.id) {
          this.productNames.set(Number(product.id), product.name || `Product #${product.id}`);
        }
      });
      this.loading = false;
    });
  }

  productName(item: OrderItem): string {
    return this.productNames.get(Number(item.product_id)) || `Product #${item.product_id}`;
  }

  billingPeriod(item: OrderItem): string {
    const freq = String(item.recurring_frequency || '').toUpperCase();
    return ({ WEEKLY: 'Weekly', MONTHLY: 'Monthly', YEARLY: 'Annual' } as Record<string, string>)[freq] || '—';
  }

  paymentDate(item: OrderItem): string {
    return item.created_at || '';
  }

  filteredSubscriptions(): OrderItem[] {
    return this.subscriptions.filter(item => {
      const status = String(item.recurring_status || '').toUpperCase();
      return !this.statusFilter || status === this.statusFilter;
    });
  }

  order(item: OrderItem): Order | undefined {
    return this.orders.find(order => order.id === item.order_id);
  }

  currency(item: OrderItem): string {
    return String(this.order(item)?.currency || '');
  }

  startDate(item: OrderItem): string {
    return formatIsoDate(item.recurring_start_date);
  }

  currentAmount(item: OrderItem): string {
    return formatMoney(item.subscription_details?.['current_amount'] ?? item.amount, this.currency(item));
  }

  statusLabel(item: OrderItem): string {
    const status = String(item.recurring_status || '').toUpperCase();
    return ({
      PENDING: 'Pending',
      ACTIVE: 'Active',
      CANCELLED: 'Cancelled',
      COMPLETED: 'Completed',
      ERROR: 'Error',
      UNKNOWN: 'Unknown'
    } as Record<string, string>)[status] || status || 'Unknown';
  }

  statusClass(item: OrderItem): string {
    return String(item.recurring_status || '').toLowerCase();
  }
}
