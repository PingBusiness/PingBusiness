import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { Inventory, ProductFile, ProductWithInventory, Store } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { CartService } from '../services/cart.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage, asArray, toNumber } from '../utils';

const MAIN_TITLE_IMAGE_DESCRIPTION = '__PINGBIZ_MAIN_TITLE_IMAGE__';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent implements OnInit, OnDestroy {
  store?: Store;
  products: ProductWithInventory[] = [];
  loading = false;
  error = '';
  notice = '';
  private imageUrls: string[] = [];

  constructor(
    private api: EstoreApiService,
    private cart: CartService,
    private router: Router,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.loading = true;
    forkJoin({
      store: this.api.getStore().pipe(catchError(err => {
        this.toast.show(apiErrorMessage(err), 'error');
        return of(undefined);
      })),
      products: this.api.getProducts().pipe(catchError(err => {
        this.toast.show(apiErrorMessage(err), 'error');
        return of([]);
      }))
    }).subscribe(({ store, products }) => {
      this.store = store;
      const live = asArray<ProductWithInventory>(products)
        .filter(product => product.state === 'A')
        .map(product => ({ ...product, inventoryLoading: true, imageLoading: true }));

      if (!live.length) {
        this.products = [];
        this.loading = false;
        return;
      }

      // Load ALL stock before rendering, so out-of-stock products never flash in
      // and then disappear — the grid appears once, already filtered.
      forkJoin(live.map(product => product.id
        ? this.api.getInventories(product.id).pipe(catchError(() => of([] as Inventory[])))
        : of([] as Inventory[])
      )).subscribe(inventoryLists => {
        live.forEach((product, index) => {
          const locations = asArray<Inventory>(inventoryLists[index]);
          product.inventory = {
            product_id: product.id,
            quantity: locations.reduce((sum, row) => sum + toNumber(row.quantity), 0),
            locations
          };
          product.inventoryLoading = false;
        });
        this.products = live;
        this.loading = false;
        this.visibleProducts().forEach(product => this.loadMainImage(product));
      });
    });
  }

  ngOnDestroy(): void {
    this.revokeImageUrls();
  }

  /** Live, in-stock products only — the first 8 for the "New Products" teaser. */
  visibleProducts(): ProductWithInventory[] {
    return this.products
      .filter(product => !(product.inventory && toNumber(product.inventory.quantity) <= 0))
      .slice(0, 8);
  }


  onAddToCart(event: { product: ProductWithInventory; quantity: number }): void {
    this.cart.add(event.product, event.quantity);
    this.toast.show(`${event.product.name || 'Item'} added to cart`);
  }

  onSubscribe(event: { product: ProductWithInventory; quantity: number }): void {
    this.router.navigate(['/subscribe', event.product.id], { queryParams: { quantity: event.quantity } });
  }

  private loadMainImage(product: ProductWithInventory): void {
    if (!product.id) {
      product.imageLoading = false;
      return;
    }

    const imageFiles = asArray<ProductFile>(product.files).filter(file => this.isImage(file));
    const mainImage = imageFiles.find(file => file.description === MAIN_TITLE_IMAGE_DESCRIPTION) || imageFiles[0];
    product.mainImageFile = mainImage;
    product.imageLoading = false;

    if (!mainImage?.id) {
      return;
    }

    this.api.getProductImage(mainImage.id).pipe(catchError(() => of(undefined))).subscribe(blob => {
      if (!blob) {
        return;
      }
      const url = URL.createObjectURL(blob);
      this.imageUrls.push(url);
      product.mainImageUrl = url;
    });
  }

  private isImage(file: ProductFile): boolean {
    return String(file.mime_type || '').toLowerCase().startsWith('image/');
  }

  private revokeImageUrls(): void {
    this.imageUrls.forEach(url => URL.revokeObjectURL(url));
    this.imageUrls = [];
  }
}
