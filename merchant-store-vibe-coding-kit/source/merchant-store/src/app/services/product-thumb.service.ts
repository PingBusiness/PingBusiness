import { Injectable } from '@angular/core';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ProductFile } from '../app.types';
import { asArray } from '../utils';
import { EstoreApiService } from './estore-api.service';

const MAIN_TITLE_IMAGE_DESCRIPTION = '__PINGBIZ_MAIN_TITLE_IMAGE__';

/**
 * Session cache of product thumbnails (object URLs) for the checkout summaries,
 * so the checkout pages can show the same line art as the cart without each
 * page re-implementing the blob fetch.
 */
@Injectable({ providedIn: 'root' })
export class ProductThumbService {
  private urls = new Map<number, string>();
  private pending = new Set<number>();

  constructor(private api: EstoreApiService) {}

  url(productId: number | undefined | null): string {
    return productId ? (this.urls.get(Number(productId)) || '') : '';
  }

  load(product: any): void {
    const productId = Number(product?.id);
    if (!productId || this.urls.has(productId) || this.pending.has(productId)) {
      return;
    }
    const images = asArray<ProductFile>(product?.files).filter(file => String(file.mime_type || '').toLowerCase().startsWith('image/'));
    const mainImage = images.find(file => file.description === MAIN_TITLE_IMAGE_DESCRIPTION) || images[0];
    if (!mainImage?.id) {
      return;
    }
    this.pending.add(productId);
    this.api.getProductImage(mainImage.id).pipe(catchError(() => of(undefined))).subscribe(blob => {
      this.pending.delete(productId);
      if (blob) {
        this.urls.set(productId, URL.createObjectURL(blob));
      }
    });
  }
}
