import { Component, OnDestroy, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { Inventory, Product, ProductFile } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { CartService } from '../services/cart.service';
import { ToastService } from '../services/toast.service';
import {
  apiErrorMessage,
  asArray,
  detailsPreview,
  formatIsoDate,
  formatMoney,
  isRecurringPlan,
  nextHongKongCalendarDate,
  recurringPlanLabel,
  recurringPlannedTotal
} from '../utils';
import { parseProductDetails } from '../product-details';

const MAIN_TITLE_IMAGE_DESCRIPTION = '__PINGBIZ_MAIN_TITLE_IMAGE__';

@Component({
  selector: 'app-product',
  templateUrl: './product.component.html',
  styleUrls: ['./product.component.css']
})
export class ProductComponent implements OnInit, OnDestroy {
  product?: Product;
  inventory?: Inventory;
  images: ProductFile[] = [];
  productFiles: ProductFile[] = [];
  selectedImage?: ProductFile;
  selectedImageUrl = '';
  loading = false;
  mediaLoading = false;
  quantity = 1;
  error = '';
  notice = '';
  private imageUrls = new Map<number, string>();

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: EstoreApiService,
    private cart: CartService,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.loading = true;
    this.route.paramMap.pipe(
      switchMap(params => {
        const id = Number(params.get('id'));
        if (!id) {
          this.toast.show('Product id is missing.', 'error');
          return of(undefined);
        }
        return this.api.getProduct(id).pipe(catchError(err => {
          this.toast.show(apiErrorMessage(err), 'error');
          return of(undefined);
        }));
      })
    ).subscribe(product => {
      this.loading = false;
      if (product && product.state !== 'A') {
        this.product = undefined;
        this.toast.show('This product is no longer available.', 'error');
        return;
      }
      this.product = product;
      if (product?.id) {
        this.api.getInventories(product.id).pipe(catchError(err => {
          this.toast.show(apiErrorMessage(err), 'error');
          return of([] as Inventory[]);
        })).subscribe(rows => {
          const locations = asArray<Inventory>(rows);
          this.inventory = {
            product_id: product.id,
            quantity: locations.reduce((sum, row) => sum + Number(row?.quantity || 0), 0),
            locations
          };
        });
        this.loadProductMedia(product);
      }
    });
  }

  ngOnDestroy(): void {
    this.revokeImageUrls();
  }

  price(): string {
    return formatMoney(this.product?.amount, this.product?.currency);
  }


  isSubscription(): boolean {
    return isRecurringPlan(this.product);
  }

  planLabel(): string {
    return recurringPlanLabel(this.product);
  }

  plannedTotal(): string {
    return formatMoney(
      recurringPlannedTotal(this.product?.amount, this.product),
      this.product?.currency
    );
  }

  firstChargeDate(): string {
    return formatIsoDate(nextHongKongCalendarDate());
  }

  /** Marketing tagline stored in the product `details` JSON envelope. */
  get tagline(): string {
    return parseProductDetails(this.product?.details).tagline || '';
  }

  description(): string {
    return detailsPreview(this.product?.description || this.tagline);
  }

  /** Full description text with the tagline as fallback (used by the description block). */
  descriptionFull(): string {
    return this.product?.description || this.tagline;
  }

  selectImage(image: ProductFile): void {
    this.selectedImage = image;
    this.selectedImageUrl = image.id ? this.imageUrls.get(image.id) || '' : '';
  }

  isSelectedImage(image: ProductFile): boolean {
    return !!image.id && this.selectedImage?.id === image.id;
  }

  private selectedIndex(): number {
    const index = this.images.findIndex(image => image.id === this.selectedImage?.id);
    return index < 0 ? 0 : index;
  }

  prevImage(): void {
    if (this.images.length < 2) {
      return;
    }
    const next = (this.selectedIndex() - 1 + this.images.length) % this.images.length;
    this.selectImage(this.images[next]);
  }

  nextImage(): void {
    if (this.images.length < 2) {
      return;
    }
    const next = (this.selectedIndex() + 1) % this.images.length;
    this.selectImage(this.images[next]);
  }

  imageUrl(image: ProductFile): string {
    return image.id ? this.imageUrls.get(image.id) || '' : '';
  }

  fileSize(file: ProductFile): string {
    const size = Number(file.size || 0);
    if (!size) {
      return '';
    }
    if (size < 1024) {
      return `${size} B`;
    }
    if (size < 1024 * 1024) {
      return `${(size / 1024).toFixed(1)} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  downloadFile(file: ProductFile): void {
    if (!file.id) {
      return;
    }
    this.api.downloadProductFile(file.id).pipe(catchError(err => {
      this.toast.show(apiErrorMessage(err), 'error');
      return of(undefined);
    })).subscribe(blob => {
      if (!blob) {
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = file.name || 'product-file';
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  maxAvailable(): number | null {
    const quantity = this.inventory?.quantity;
    return quantity === undefined || quantity === null ? null : Math.max(0, Number(quantity) || 0);
  }

  quantityExceedsStock(): boolean {
    const max = this.maxAvailable();
    return max !== null && Math.max(1, Number(this.quantity) || 1) > max;
  }

  /**
   * Loaded and nothing sellable (0 stock, or no inventory rows) → unavailable.
   * The store can't sell it, so the actions become a single disabled
   * "Unavailable" button instead of an Add to Cart that would fail.
   */
  isUnavailable(): boolean {
    return !!this.inventory && (Number(this.inventory.quantity) || 0) <= 0;
  }

  addToCart(): void {
    if (!this.product || this.isSubscription()) {
      return;
    }
    if (this.quantityExceedsStock()) {
      this.toast.show('The requested quantity is unavailable.', 'error');
      return;
    }
    this.error = '';
    this.cart.add(this.product, Math.max(1, Math.trunc(Number(this.quantity) || 1)));
    this.toast.show(`${this.product.name || 'Item'} added to cart`);
  }

  buyNow(): void {
    if (this.isSubscription()) {
      this.subscribeNow();
      return;
    }
    this.addToCart();
    this.router.navigate(['/cart']);
  }

  subscribeNow(): void {
    if (!this.product?.id || !this.isSubscription()) {
      return;
    }
    if (this.quantityExceedsStock()) {
      this.toast.show('The requested quantity is unavailable.', 'error');
      return;
    }
    this.router.navigate(['/subscribe', this.product.id], {
      queryParams: { quantity: Math.max(1, Math.trunc(Number(this.quantity) || 1)) }
    });
  }

  inventoryLocations(): Inventory[] {
    return this.inventory?.locations || [];
  }

  hasInventoryBreakdown(): boolean {
    return this.inventoryLocations().length > 0;
  }

  private loadProductMedia(product: Product): void {
    this.mediaLoading = true;
    this.revokeImageUrls();
    this.images = [];
    this.productFiles = [];
    this.selectedImage = undefined;
    this.selectedImageUrl = '';

    const allFiles = asArray<ProductFile>(product.files);
    const imageFiles = allFiles.filter(file => this.isImage(file));
    const mainImage = imageFiles.find(file => file.description === MAIN_TITLE_IMAGE_DESCRIPTION);
    const additionalImages = imageFiles.filter(file => file.id !== mainImage?.id);
    this.images = mainImage ? [mainImage, ...additionalImages] : additionalImages;
    this.productFiles = allFiles.filter(file => !this.isImage(file));
    this.mediaLoading = false;

    this.images.forEach(image => this.loadImagePreview(image));
    if (this.images.length) {
      this.selectedImage = this.images[0];
    }
  }

  private loadImagePreview(image: ProductFile): void {
    if (!image.id) {
      return;
    }
    this.api.getProductImage(image.id).pipe(catchError(() => of(undefined))).subscribe(blob => {
      if (!blob || !image.id) {
        return;
      }
      const oldUrl = this.imageUrls.get(image.id);
      if (oldUrl) {
        URL.revokeObjectURL(oldUrl);
      }
      const url = URL.createObjectURL(blob);
      this.imageUrls.set(image.id, url);
      if (this.selectedImage?.id === image.id || (!this.selectedImageUrl && this.selectedImage?.id === image.id)) {
        this.selectedImageUrl = url;
      }
    });
  }

  private isImage(file: ProductFile): boolean {
    return String(file.mime_type || '').toLowerCase().startsWith('image/');
  }

  private revokeImageUrls(): void {
    this.imageUrls.forEach(url => URL.revokeObjectURL(url));
    this.imageUrls.clear();
  }
}
