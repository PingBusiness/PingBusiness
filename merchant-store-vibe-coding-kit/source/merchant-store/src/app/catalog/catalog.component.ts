import { Component, OnDestroy, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { catchError } from 'rxjs/operators';
import { forkJoin, of } from 'rxjs';

import { Inventory, ProductFile, ProductWithInventory } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { CartService } from '../services/cart.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage, asArray, isRecurringPlan, toNumber } from '../utils';
import { parseProductDetails } from '../product-details';

const MAIN_TITLE_IMAGE_DESCRIPTION = '__PINGBIZ_MAIN_TITLE_IMAGE__';

@Component({
  selector: 'app-catalog',
  templateUrl: './catalog.component.html',
  styleUrls: ['./catalog.component.css']
})
export class CatalogComponent implements OnInit, OnDestroy {
  products: ProductWithInventory[] = [];
  query = '';
  sort = 'name';
  typeFilter = '';
  readonly pageSize = 20;
  currentPage = 1;
  loading = false;
  error = '';
  notice = '';
  private imageUrls: string[] = [];

  constructor(
    private route: ActivatedRoute,
    private api: EstoreApiService,
    private cart: CartService,
    private router: Router,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.route.queryParamMap.subscribe(params => {
      this.query = params.get('q') || '';
    });
    this.loadProducts();
  }

  ngOnDestroy(): void {
    this.revokeImageUrls();
  }

  loadProducts(): void {
    this.loading = true;
    this.error = '';
    this.revokeImageUrls();
    this.api.getProducts().pipe(
      catchError(err => {
        this.toast.show(apiErrorMessage(err), 'error');
        return of([]);
      })
    ).subscribe(products => {
      const live = asArray<ProductWithInventory>(products)
        .filter(product => product.state === 'A')
        .map(product => ({ ...product, inventoryLoading: true, imageLoading: true }));

      if (!live.length) {
        this.products = [];
        this.loading = false;
        this.currentPage = 1;
        return;
      }

      // Load ALL stock before rendering so out-of-stock products don't flash in
      // and then vanish once inventory resolves.
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
        this.currentPage = 1;
        this.loadImagesForCurrentPage();
      });
    });
  }

  filteredProducts(): ProductWithInventory[] {
    const q = this.query.trim().toLowerCase();
    let result = this.products.filter(product => {
      // Don't show unavailable (out-of-stock) products at all: once inventory is
      // known and totals zero (or has no rows), the store can't sell it, so hide
      // it rather than offering an "Add to Cart" that fails. Still-loading
      // products are shown until their stock is known.
      if (product.inventory && toNumber(product.inventory.quantity) <= 0) {
        return false;
      }
      const recurring = isRecurringPlan(product);
      if (this.typeFilter === 'one_time' && recurring) {
        return false;
      }
      if (this.typeFilter === 'subscription' && !recurring) {
        return false;
      }
      if (!q) {
        return true;
      }
      return `${product.name || ''} ${product.description || ''} ${parseProductDetails(product.details).tagline || ''} ${product.identifier || ''} ${product.recurring_frequency || ''}`
        .toLowerCase()
        .includes(q);
    });
    result = [...result];
    if (this.sort === 'priceLow') {
      result.sort((a, b) => toNumber(a.amount) - toNumber(b.amount));
    } else if (this.sort === 'priceHigh') {
      result.sort((a, b) => toNumber(b.amount) - toNumber(a.amount));
    } else {
      result.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));
    }
    return result;
  }

  pagedProducts(): ProductWithInventory[] {
    const products = this.filteredProducts();
    const totalPages = Math.max(1, Math.ceil(products.length / this.pageSize));
    const page = Math.min(Math.max(this.currentPage, 1), totalPages);
    const start = (page - 1) * this.pageSize;
    return products.slice(start, start + this.pageSize);
  }

  totalProducts(): number {
    return this.filteredProducts().length;
  }

  totalPages(): number {
    return Math.max(1, Math.ceil(this.totalProducts() / this.pageSize));
  }

  pageStart(): number {
    const total = this.totalProducts();
    return total === 0 ? 0 : (this.normalizedPage() - 1) * this.pageSize + 1;
  }

  pageEnd(): number {
    return Math.min(this.normalizedPage() * this.pageSize, this.totalProducts());
  }

  onFilterChange(): void {
    this.currentPage = 1;
    this.loadImagesForCurrentPage();
  }

  onSortChange(): void {
    this.currentPage = 1;
    this.loadImagesForCurrentPage();
  }

  goToPage(page: number): void {
    const nextPage = Math.min(Math.max(page, 1), this.totalPages());
    if (nextPage === this.currentPage) {
      return;
    }
    this.currentPage = nextPage;
    this.loadImagesForCurrentPage();
  }

  add(event: { product: ProductWithInventory; quantity: number }): void {
    if (isRecurringPlan(event.product)) {
      this.subscribe(event);
      return;
    }
    this.cart.add(event.product, event.quantity);
    this.toast.show(`${event.quantity} × ${event.product.name || 'item'} added to cart`);
  }

  subscribe(event: { product: ProductWithInventory; quantity: number }): void {
    const productId = Number(event.product.id);
    if (!productId || !isRecurringPlan(event.product)) {
      return;
    }
    this.router.navigate(['/subscribe', productId], { queryParams: { quantity: event.quantity } });
  }

  private loadImagesForCurrentPage(): void {
    this.revokeImageUrls();
    this.products.forEach(product => {
      product.mainImageFile = undefined;
      product.mainImageUrl = undefined;
      product.imageLoading = false;
    });

    this.pagedProducts().forEach(product => {
      product.imageLoading = true;
      this.loadMainImage(product);
    });
  }

  private normalizedPage(): number {
    return Math.min(Math.max(this.currentPage, 1), this.totalPages());
  }

  private isProductOnCurrentPage(product: ProductWithInventory): boolean {
    return this.pagedProducts().some(pageProduct => pageProduct.id === product.id);
  }

  private loadMainImage(product: ProductWithInventory): void {
    if (!product.id) {
      product.imageLoading = false;
      return;
    }

    const imageFiles = asArray<ProductFile>(product.files).filter(file => this.isImage(file));
    const mainImage = imageFiles.find(file => file.description === MAIN_TITLE_IMAGE_DESCRIPTION) || imageFiles[0];
    if (!this.isProductOnCurrentPage(product)) {
      return;
    }
    product.mainImageFile = mainImage;
    product.imageLoading = false;

    if (!mainImage?.id) {
      return;
    }

    this.api.getProductImage(mainImage.id).pipe(catchError(() => of(undefined))).subscribe(blob => {
      if (!blob) {
        return;
      }
      if (!this.isProductOnCurrentPage(product)) {
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
