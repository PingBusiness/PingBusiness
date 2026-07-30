export interface ApiRecord {
  [key: string]: any;
}

export interface HealthResponse {
  status: string;
  service: string;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
  refresh_expires_in?: number;
  token_type?: string;
  scope?: string;
  [key: string]: any;
}

export interface AuthSession extends AuthTokenResponse {
  username?: string;
  created_at: number;
  access_expires_at?: number;
  refresh_expires_at?: number;
}

export interface Customer {
  id?: number;
  identifier?: string;
  merchant_id?: number;
  first_name?: string;
  last_name?: string;
  details?: string;
  shipping_address?: string;
  billing_address?: string;
  email?: string;
  phone?: string;
  username?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PaymentNetworksResponse {
  payment_gateway: string;
  payment_networks: string[];
}

export interface Store {
  id?: number;
  identifier?: string;
  merchant_id?: number;
  name?: string;
  details?: string;
  mode?: string;
  created_at?: string;
  updated_at?: string;
}

export type RecurringFrequency = 'WEEKLY' | 'MONTHLY' | 'YEARLY';

export interface RecurringPlan {
  recurring_frequency?: RecurringFrequency | string | null;
  recurring_intervals?: number | null;
  recurring_total_execution_times?: number | null;
}

export interface Product extends RecurringPlan {
  id?: number;
  identifier?: string;
  store_id?: number;
  name?: string;
  details?: string;
  description?: string;
  amount?: number | string;
  currency?: string;
  state?: string;
  files?: ProductFile[];
  created_at?: string;
  updated_at?: string;
}

export interface ProductFile {
  id?: number;
  merchant_id?: number;
  product_id?: number;
  name?: string;
  description?: string;
  location?: string;
  size?: number | string;
  mime_type?: string;
  created_at?: string;
  previewUrl?: string;
}

export interface Inventory {
  id?: number;
  product_id?: number;
  quantity?: number;
  location?: string;
  updated_at?: string;
  locations?: Inventory[];
}

export interface ProductWithInventory extends Product {
  inventory?: Inventory;
  mainImageFile?: ProductFile;
  mainImageUrl?: string;
  imageLoading?: boolean;
  inventoryLoading?: boolean;
  inventoryError?: string;
}

export interface CartLine {
  product_id: number;
  quantity: number;
  product: Product;
  added_at: number;
}

export interface Order {
  id?: number;
  identifier?: string;
  merchant_id?: number;
  customer_id?: number;
  store_id?: number;
  status?: string;
  currency?: string;
  subtotal_amount?: number | string;
  total_amount?: number | string;
  details?: string;
  created_at?: string;
  updated_at?: string;
}

export interface OrderItem extends RecurringPlan {
  id?: number;
  order_id?: number;
  order_status?: string;
  product_id?: number;
  quantity?: number;
  unit_amount?: number | string;
  amount?: number | string;
  recurring_start_date?: string | null;
  recurring_merchant_reference?: string | null;
  recurring_status?: string | null;
  subscription_details?: Record<string, any> | null;
  state?: string | null;
  details?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Payment {
  id?: number;
  identifier?: string;
  order_id?: number;
  merchant_id?: number;
  store_id?: number;
  currency?: string;
  amount?: number | string;
  status?: string;
  reference?: string;
  details?: string;
  created_at?: string;
}

export interface CheckoutPayload {
  cart: Array<{ product_id: number; quantity: number }>;
  network: string;
  lang?: string;
  subject?: string;
  customer_state?: string;
  customer_country?: string;
  customer_postal_code?: string;
  response_mode?: 'html' | 'json';
}

export interface CheckoutLaunch {
  checkout_id: string;
  checkout_reference: string;
  action_url: string;
  fields: Record<string, string | number | boolean | null>;
}

export interface SubscribePayload {
  product_id: number;
  quantity: number;
  subject?: string;
  token_valid_date?: string;
}

export interface CheckoutStatus {
  checkout_id?: string;
  complete?: boolean;
  success?: boolean;
  status?: string;
  order_id?: number | null;
  payment_reference?: string | null;
  checkout_reference?: string | null;
  paymentasia_status?: string | null;
  recurring_checkout_status?: string | null;
}
