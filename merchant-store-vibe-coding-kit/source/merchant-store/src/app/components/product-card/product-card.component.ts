import { Component, EventEmitter, Input, Output } from '@angular/core';

import { ProductWithInventory } from '../../app.types';
import {
  detailsPreview,
  formatMoney,
  isRecurringPlan,
  recurringCadenceLabel,
  recurringPlanLabel,
  recurringPlannedTotal,
  toNumber
} from '../../utils';
import { parseProductDetails } from '../../product-details';

@Component({
  selector: 'app-product-card',
  templateUrl: './product-card.component.html',
  styleUrls: ['./product-card.component.css']
})
export class ProductCardComponent {
  @Input() product!: ProductWithInventory;
  @Output() addToCart = new EventEmitter<{ product: ProductWithInventory; quantity: number }>();
  @Output() subscribeNow = new EventEmitter<{ product: ProductWithInventory; quantity: number }>();

  quantity = 1;

  get availabilityText(): string {
    if (this.product?.inventoryLoading) {
      return 'Checking availability...';
    }
    if (this.product?.inventoryError) {
      return this.product.inventoryError;
    }
    const quantity = this.product?.inventory?.quantity;
    if (quantity === undefined || quantity === null) {
      return 'Available';
    }
    return quantity > 0 ? 'Available' : 'Unavailable';
  }

  get inStock(): boolean {
    const quantity = this.product?.inventory?.quantity;
    return quantity === undefined || quantity === null ? true : quantity > 0;
  }

  get maxAvailable(): number | null {
    const quantity = this.product?.inventory?.quantity;
    return quantity === undefined || quantity === null ? null : Math.max(0, Number(quantity) || 0);
  }

  get quantityExceedsStock(): boolean {
    return this.maxAvailable !== null && Math.max(1, Number(this.quantity) || 1) > this.maxAvailable;
  }

  get inventoryBreakdown(): string {
    const rows = this.product?.inventory?.locations || [];
    if (!rows.length) {
      return '';
    }
    const parts = rows
      .filter(row => Number(row.quantity || 0) > 0)
      .map(row => `${row.location || 'Default'}: ${Number(row.quantity || 0)}`);
    return parts.length ? 'Available' : 'Unavailable';
  }

  get recurring(): boolean {
    return isRecurringPlan(this.product);
  }

  price(): string {
    return formatMoney(this.product?.amount, this.product?.currency);
  }

  amountNumber(): number {
    return toNumber(this.product?.amount);
  }

  preview(): string {
    return detailsPreview(this.product?.description || parseProductDetails(this.product?.details).tagline || '');
  }

  planLabel(): string {
    return recurringPlanLabel(this.product);
  }

  cadenceLabel(): string {
    return recurringCadenceLabel(this.product);
  }

  plannedTotal(): string {
    return formatMoney(recurringPlannedTotal(this.product?.amount, this.product), this.product?.currency);
  }

  act(): void {
    if (!this.product || !this.inStock || this.quantityExceedsStock) {
      return;
    }
    const event = { product: this.product, quantity: Math.max(1, Math.trunc(Number(this.quantity) || 1)) };
    if (this.recurring) {
      this.subscribeNow.emit(event);
    } else {
      this.addToCart.emit(event);
      this.quantity = 1;
    }
  }
}
