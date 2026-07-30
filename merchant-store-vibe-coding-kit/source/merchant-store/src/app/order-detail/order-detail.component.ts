import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { ORDER_STATUS_LABELS } from '../app.constants';
import { Order, OrderItem, Payment } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { ToastService } from '../services/toast.service';
import {
  apiErrorMessage,
  asArray,
  formatIsoDate,
  formatMoney,
  isRecurringPlan,
  recurringPlanLabel,
  toCents
} from '../utils';

@Component({
  selector: 'app-order-detail',
  templateUrl: './order-detail.component.html',
  styleUrls: ['./order-detail.component.css']
})
export class OrderDetailComponent implements OnInit {
  order?: Order;
  items: OrderItem[] = [];
  payments: Payment[] = [];
  loading = false;
  error = '';

  constructor(
    private route: ActivatedRoute,
    private api: EstoreApiService,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = '';
    this.route.paramMap.pipe(
      switchMap(params => {
        const orderId = Number(params.get('id'));
        if (!orderId) {
          this.toast.show('Order id is missing.', 'error');
          return of(undefined);
        }
        return forkJoin({
          order: this.api.getOrder(orderId),
          items: this.api.getOrderItems({ order_id: orderId }).pipe(catchError(() => of([]))),
          payments: this.api.getPayments({ order_id: orderId }).pipe(catchError(() => of([])))
        }).pipe(catchError(err => {
          this.toast.show(apiErrorMessage(err), 'error');
          return of(undefined);
        }));
      })
    ).subscribe(result => {
      if (result) {
        this.order = result.order;
        this.items = asArray<OrderItem>(result.items);
        this.payments = asArray<Payment>(result.payments);
      }
      this.loading = false;
    });
  }

  statusLabel(status?: string): string {
    return status ? (ORDER_STATUS_LABELS[status] || status) : 'Unknown';
  }

  orderAmount(): string {
    return formatMoney(this.order?.total_amount, this.order?.currency);
  }

  itemAmount(item: OrderItem): string {
    return formatMoney(item.amount, this.order?.currency);
  }

  itemStateLabel(item: OrderItem): string {
    return String(item.state || '').toUpperCase() === 'D' ? 'Delivered' : 'Not delivered';
  }

  paymentAmount(payment: Payment): string {
    return formatMoney(payment.amount, payment.currency);
  }

  isSubscription(item: OrderItem): boolean {
    return isRecurringPlan(item);
  }

  hasSubscriptions(): boolean {
    return this.items.some(item => this.isSubscription(item));
  }

  orderKindLabel(): string {
    return this.hasSubscriptions() ? 'Subscription order' : 'One-time purchase order';
  }

  planLabel(item: OrderItem): string {
    return recurringPlanLabel(item);
  }

  recurringStartDate(item: OrderItem): string {
    return formatIsoDate(item.recurring_start_date);
  }

  recurringStatusLabel(item: OrderItem): string {
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

  plannedCommitment(): string {
    // Sum in integer cents (price × executions), convert once — no float drift.
    const cents = this.items.reduce((total, item) => {
      const executions = Math.max(1, Number(item.recurring_total_execution_times) || 1);
      return total + toCents(item.amount) * executions;
    }, 0);
    return formatMoney(cents / 100, this.order?.currency);
  }

  currentSubscriptionAmount(item: OrderItem): string {
    const value = item.subscription_details?.['current_amount'] ?? item.amount;
    return formatMoney(value, this.order?.currency);
  }
}
