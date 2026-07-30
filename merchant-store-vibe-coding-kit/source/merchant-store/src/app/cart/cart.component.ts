import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { forkJoin, of, Subscription } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { CartLine, Inventory, ProductFile } from '../app.types';
import { CartService } from '../services/cart.service';
import { EstoreApiService } from '../services/estore-api.service';
import { KeycloakService } from '../services/keycloak.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage, asArray, formatMoney, isRecurringPlan, toNumber } from '../utils';

const MAIN_TITLE_IMAGE_DESCRIPTION = '__PINGBIZ_MAIN_TITLE_IMAGE__';

@Component({
  selector: 'app-cart',
  templateUrl: './cart.component.html',
  styleUrls: ['./cart.component.css']
})
export class CartComponent implements OnInit, OnDestroy {
  items: CartLine[] = [];
  authenticated = false;
  imageError = '';
  checkoutError = '';
  cartNotice = '';
  checkoutLoading = false;
  cartLineErrors: Record<number, string> = {};
  /** Latest known available stock per product line, for the "N in stock" hint. */
  cartLineStock: Record<number, number> = {};
  private subscriptions: Subscription[] = [];
  private imageUrls = new Map<number, string>();
  private validatedProductIds = new Set<number>();

  constructor(
    public cart: CartService,
    private api: EstoreApiService,
    private keycloak: KeycloakService,
    private router: Router,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.subscriptions.push(this.cart.items$.subscribe(items => {
      this.items = items;
      this.refreshCartProducts();
      this.loadCartImages();
      // Detect insufficient stock now (not only at checkout) so the line shows a
      // warning and checkout is blocked before the user gets there.
      this.revalidateInventory();
    }));
    this.subscriptions.push(this.keycloak.authState$.subscribe(() => this.authenticated = this.keycloak.isAuthenticated()));
    this.authenticated = this.keycloak.isAuthenticated();
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach(subscription => subscription.unsubscribe());
    this.revokeImageUrls();
  }

  currency(): string {
    return String(this.items[0]?.product.currency || '');
  }

  subtotal(): string {
    return formatMoney(this.cart.subtotal(this.items), this.currency());
  }

  lineTotal(item: CartLine): string {
    return formatMoney(this.cart.lineTotal(item), item.product.currency);
  }

  imageUrl(item: CartLine): string {
    return this.imageUrls.get(item.product_id) || '';
  }

  update(item: CartLine, quantity: any): void {
    this.checkoutError = '';
    // Typed input can be empty/0/negative — clamp to a whole number ≥ 1 (Remove
    // is the way to take an item out, not quantity 0).
    const qty = Math.max(1, Math.trunc(Number(quantity)) || 1);
    // Update the per-line error SYNCHRONOUSLY from the stock we already know, so
    // the message doesn't blink off then on while the async re-check is in flight.
    const known = this.cartLineStock[item.product_id];
    if (known !== undefined && qty > known) {
      this.cartLineErrors[item.product_id] = 'The requested quantity is unavailable.';
    } else {
      delete this.cartLineErrors[item.product_id];
    }
    this.cart.updateQuantity(item.product_id, qty);
  }

  /** Keep DOM (and loaded images) stable across quantity changes — no flicker. */
  trackByProductId(_index: number, item: CartLine): number {
    return item.product_id;
  }

  lineError(item: CartLine): string {
    return this.cartLineErrors[item.product_id] || '';
  }

  /** Remaining stock for the line, or null until it has been checked. */
  lineStock(item: CartLine): number | null {
    const value = this.cartLineStock[item.product_id];
    return value === undefined ? null : value;
  }

  /** "N in stock" hint shown under each product; '' while stock is unknown. */
  lineStockLabel(item: CartLine): string {
    const stock = this.lineStock(item);
    if (stock === null) {
      return '';
    }
    if (stock <= 0) {
      return 'Out of stock';
    }
    return `${stock} in stock`;
  }

  /** True when any line exceeds available stock — used to block checkout early. */
  hasStockError(): boolean {
    return Object.keys(this.cartLineErrors).length > 0;
  }

  /** Re-checks stock for the current cart, populating per-line errors. */
  private revalidateInventory(): void {
    if (!this.items.length) {
      this.cartLineErrors = {};
      this.cartLineStock = {};
      return;
    }
    this.validateCartInventory().subscribe({ error: () => undefined });
  }

  remove(item: CartLine): void {
    this.checkoutError = '';
    delete this.cartLineErrors[item.product_id];
    delete this.cartLineStock[item.product_id];
    this.revokeImageUrl(item.product_id);
    this.validatedProductIds.delete(item.product_id);
    this.cart.remove(item.product_id);
  }

  checkout(): void {
    if (this.checkoutLoading) {
      return;
    }
    this.checkoutError = '';
    this.cartLineErrors = {};

    if (this.items.length === 0) {
      this.toast.show('Your cart is empty.', 'error');
      return;
    }
    if (this.items.some(item => isRecurringPlan(item.product))) {
      this.toast.show('Subscriptions cannot be placed in the cart. Use Subscribe Now on the subscription product.', 'error');
      return;
    }

    const currencies = new Set(this.items.map(item => String(item.product.currency || '').toUpperCase()));
    if (currencies.size !== 1 || currencies.has('')) {
      this.toast.show('All cart items must use the same currency.', 'error');
      return;
    }

    this.checkoutLoading = true;
    this.validateCartInventory().subscribe({
      next: inventoryError => {
        this.checkoutLoading = false;
        if (inventoryError) {
          this.toast.show(inventoryError, 'error');
          return;
        }
        if (!this.authenticated) {
          this.router.navigate(['/signin'], { queryParams: { returnUrl: '/checkout' } });
          return;
        }
        this.router.navigate(['/checkout']);
      },
      error: err => {
        this.checkoutLoading = false;
        this.toast.show(apiErrorMessage(err), 'error');
      }
    });
  }

  private validateCartInventory() {
    const checks = this.items.map(item => this.api.getInventories(item.product_id).pipe(
      map(rows => {
        const available = asArray<Inventory>(rows).reduce((sum, row) => sum + toNumber(row?.quantity), 0);
        return { item, available, error: '' };
      }),
      catchError(err => of({ item, available: 0, error: apiErrorMessage(err) }))
    ));

    return forkJoin(checks).pipe(map(results => {
      // Update stock hint + line error IN PLACE per product (never reset the whole
      // map), so a line's message can't blink off-and-on between checks.
      results.forEach(result => {
        if (result.error) {
          return;
        }
        this.cartLineStock[result.item.product_id] = result.available;
        if (result.item.quantity > result.available) {
          this.cartLineErrors[result.item.product_id] = 'The requested quantity is unavailable.';
        } else {
          delete this.cartLineErrors[result.item.product_id];
        }
      });

      const inventoryReadError = results.find(result => result.error);
      if (inventoryReadError) {
        return inventoryReadError.error || 'Could not verify inventory. Please try again.';
      }

      const insufficient = results.find(result => result.item.quantity > result.available);
      if (!insufficient) {
        return '';
      }
      const name = insufficient.item.product?.name || `product ${insufficient.item.product_id}`;
      return `${name} is unavailable in the requested quantity. Please update your cart before checkout.`;
    }));
  }

  private refreshCartProducts(): void {
    this.items.forEach(item => {
      if (!item.product_id || this.validatedProductIds.has(item.product_id)) {
        return;
      }
      this.validatedProductIds.add(item.product_id);
      this.api.getProduct(item.product_id).pipe(
        catchError(err => {
          const unavailable = err?.status === 403 || err?.status === 404;
          if (unavailable) {
            const name = item.product?.name || `Product ${item.product_id}`;
            this.revokeImageUrl(item.product_id);
            this.cart.remove(item.product_id);
            this.toast.show(`${name} is no longer available and was removed from your cart.`, 'info');
          } else {
            this.toast.show(`Could not refresh ${item.product?.name || `product ${item.product_id}`}: ${apiErrorMessage(err)}`, 'error');
          }
          return of(undefined);
        })
      ).subscribe(product => {
        if (!product) {
          return;
        }
        if (product.state !== 'A' || isRecurringPlan(product)) {
          const name = product.name || item.product?.name || `Product ${item.product_id}`;
          this.revokeImageUrl(item.product_id);
          this.cart.remove(item.product_id);
          this.toast.show(isRecurringPlan(product)
            ? `${name} is a subscription and was removed from your cart. Use Subscribe Now instead.`
            : `${name} is no longer available and was removed from your cart.`, 'info');
          return;
        }
        this.revokeImageUrl(item.product_id);
        this.cart.setProduct(product);
      });
    });
  }

  private loadCartImages(): void {
    const activeProductIds = new Set(this.items.map(item => item.product_id));
    Array.from(this.imageUrls.keys()).forEach(productId => {
      if (!activeProductIds.has(productId)) {
        this.revokeImageUrl(productId);
      }
    });

    this.items.forEach(item => {
      if (this.imageUrls.has(item.product_id)) {
        return;
      }
      const mainImage = this.mainImageForProduct(item.product);
      if (!mainImage?.id) {
        return;
      }
      this.api.getProductImage(mainImage.id).pipe(catchError(() => of(undefined))).subscribe(blob => {
        if (!blob || !this.items.some(current => current.product_id === item.product_id)) {
          return;
        }
        this.revokeImageUrl(item.product_id);
        this.imageUrls.set(item.product_id, URL.createObjectURL(blob));
      });
    });
  }

  private mainImageForProduct(product: any): ProductFile | undefined {
    const images = asArray<ProductFile>(product?.files).filter(file => String(file.mime_type || '').toLowerCase().startsWith('image/'));
    return images.find(file => file.description === MAIN_TITLE_IMAGE_DESCRIPTION) || images[0];
  }

  private revokeImageUrl(productId: number): void {
    const url = this.imageUrls.get(productId);
    if (url) {
      URL.revokeObjectURL(url);
      this.imageUrls.delete(productId);
    }
  }

  private revokeImageUrls(): void {
    this.imageUrls.forEach(url => URL.revokeObjectURL(url));
    this.imageUrls.clear();
  }
}
