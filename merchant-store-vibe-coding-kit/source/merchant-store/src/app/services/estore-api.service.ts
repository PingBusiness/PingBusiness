import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { APP_URL } from '../app.configs';
import { CheckoutLaunch, CheckoutPayload, CheckoutStatus, Customer, HealthResponse, Inventory, Order, OrderItem, Payment, PaymentNetworksResponse, Product, Store, SubscribePayload } from '../app.types';
import { KeycloakService } from './keycloak.service';

@Injectable({ providedIn: 'root' })
export class EstoreApiService {
  private readonly baseUrl = APP_URL.replace(/\/$/, '');

  constructor(private http: HttpClient, private keycloak: KeycloakService) {}

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(this.url('/health'));
  }

  createCustomer(body: Partial<Customer> & { password?: string; username?: string }): Observable<any> {
    return this.http.post(this.url('/customer'), body);
  }

  getCustomer(): Observable<Customer> {
    return this.keycloak.get(this.url('/customer')) as Observable<Customer>;
  }

  updateCustomer(body: Partial<Customer> & { id: number }): Observable<Customer | any> {
    return this.keycloak.post(this.url('/customer'), body);
  }

  updatePassword(currentPassword: string, newPassword: string): Observable<any> {
    return this.keycloak.post(this.url('/customer/update_password'), {
      current_password: currentPassword,
      new_password: newPassword
    });
  }

  getPaymentNetworks(): Observable<PaymentNetworksResponse> {
    return this.http.get<PaymentNetworksResponse>(this.url('/payment_networks'));
  }

  getStore(storeId?: number): Observable<Store> {
    return this.http.get<Store>(storeId ? this.url(`/store/${storeId}`) : this.url('/store'));
  }

  getProducts(params?: Record<string, any>): Observable<Product[]> {
    return this.http.get<Product[]>(this.url('/products', { ...(params || {}), state: 'A' }));
  }

  getProduct(productId: number): Observable<Product> {
    return this.http.get<Product>(this.url(`/product/${productId}`));
  }

  getInventories(productId: number): Observable<Inventory[]> {
    return this.http.get<Inventory[]>(this.url('/inventories', { product_id: productId }));
  }

  getProductImage(fileId: number): Observable<Blob> {
    return this.http.get(this.url(`/image/${fileId}`), { responseType: 'blob' });
  }

  downloadProductFile(fileId: number): Observable<Blob> {
    return this.http.get(this.url('/download', { file_id: fileId }), { responseType: 'blob' });
  }

  getOrders(params?: Record<string, any>): Observable<Order[]> {
    return this.keycloak.get(this.url('/orders', params)) as Observable<Order[]>;
  }

  getOrder(orderId: number): Observable<Order> {
    return this.keycloak.get(this.url(`/order/${orderId}`)) as Observable<Order>;
  }


  getOrderItems(params?: Record<string, any>): Observable<OrderItem[]> {
    return this.keycloak.get(this.url('/order_items', params)) as Observable<OrderItem[]>;
  }

  getOrderItem(orderItemId: number): Observable<OrderItem> {
    return this.keycloak.get(this.url(`/order_item/${orderItemId}`)) as Observable<OrderItem>;
  }


  getPayments(params?: Record<string, any>): Observable<Payment[]> {
    return this.keycloak.get(this.url('/payments', params)) as Observable<Payment[]>;
  }

  getPayment(paymentId: number): Observable<Payment> {
    return this.keycloak.get(this.url(`/payment/${paymentId}`)) as Observable<Payment>;
  }


  checkout(payload: CheckoutPayload): Observable<CheckoutLaunch> {
    return this.keycloak.post(this.url('/checkout'), payload) as Observable<CheckoutLaunch>;
  }

  subscribe(payload: SubscribePayload): Observable<string> {
    return this.keycloak.post(this.url('/subscribe'), payload, 'text') as Observable<string>;
  }

  checkoutStatus(checkoutId: string): Observable<CheckoutStatus> {
    return this.keycloak.get(this.url(`/checkout/status/${encodeURIComponent(checkoutId)}`)) as Observable<CheckoutStatus>;
  }

  checkoutReturnUrl(checkoutId: string, params?: Record<string, any>): string {
    return this.url(`/checkout/return/${encodeURIComponent(checkoutId)}`, params);
  }

  checkoutNotify(checkoutId: string, payload: Record<string, any>): Observable<any> {
    return this.http.post(this.url(`/checkout/notify/${encodeURIComponent(checkoutId)}`), payload);
  }

  private url(path: string, params?: Record<string, any>): string {
    const query = this.queryString(params);
    return `${this.baseUrl}${path}${query}`;
  }

  private queryString(params?: Record<string, any>): string {
    const parts: string[] = [];
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
      }
    });
    return parts.length ? `?${parts.join('&')}` : '';
  }
}
