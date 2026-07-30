import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { map } from 'rxjs/operators';

import { CART_STORAGE_KEY } from '../app.constants';
import { CartLine, Product } from '../app.types';
import { isRecurringPlan, toNumber } from '../utils';

@Injectable({ providedIn: 'root' })
export class CartService {
  private readonly itemsSubject = new BehaviorSubject<CartLine[]>(this.load());

  readonly items$ = this.itemsSubject.asObservable();
  readonly count$ = this.items$.pipe(map(items => items.reduce((sum, item) => sum + item.quantity, 0)));
  readonly subtotal$ = this.items$.pipe(map(items => this.subtotal(items)));

  getSnapshot(): CartLine[] {
    return this.itemsSubject.value;
  }

  add(product: Product, quantity = 1): void {
    const productId = Number(product.id);
    if (!productId || quantity <= 0 || isRecurringPlan(product)) {
      return;
    }
    const current = [...this.itemsSubject.value];
    const existing = current.find(item => item.product_id === productId);
    if (existing) {
      existing.quantity += quantity;
      existing.product = product;
    } else {
      current.push({
        product_id: productId,
        quantity,
        product,
        added_at: Date.now()
      });
    }
    this.persist(current);
  }

  updateQuantity(productId: number, quantity: number): void {
    if (quantity <= 0) {
      this.remove(productId);
      return;
    }
    const current = this.itemsSubject.value.map(item =>
      item.product_id === productId ? { ...item, quantity } : item
    );
    this.persist(current);
  }

  setProduct(product: Product): void {
    const productId = Number(product.id);
    if (!productId) {
      return;
    }
    if (isRecurringPlan(product)) {
      this.remove(productId);
      return;
    }
    const current = this.itemsSubject.value.map(item =>
      item.product_id === productId ? { ...item, product } : item
    );
    this.persist(current);
  }

  remove(productId: number): void {
    this.persist(this.itemsSubject.value.filter(item => item.product_id !== productId));
  }

  clear(): void {
    this.persist([]);
  }

  lineTotal(item: CartLine): number {
    return toNumber(item.product.amount) * item.quantity;
  }

  subtotal(items = this.itemsSubject.value): number {
    return items.reduce((sum, item) => sum + this.lineTotal(item), 0);
  }

  private load(): CartLine[] {
    const raw = sessionStorage.getItem(CART_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    try {
      const parsed = JSON.parse(raw);
      const ordinaryItems = Array.isArray(parsed)
        ? parsed.filter(item => item?.product_id && item?.quantity > 0 && !isRecurringPlan(item?.product))
        : [];
      sessionStorage.setItem(CART_STORAGE_KEY, JSON.stringify(ordinaryItems));
      return ordinaryItems;
    } catch (_) {
      sessionStorage.removeItem(CART_STORAGE_KEY);
      return [];
    }
  }

  private persist(items: CartLine[]): void {
    const ordinaryItems = items.filter(item => !isRecurringPlan(item.product));
    sessionStorage.setItem(CART_STORAGE_KEY, JSON.stringify(ordinaryItems));
    this.itemsSubject.next(ordinaryItems);
  }
}
