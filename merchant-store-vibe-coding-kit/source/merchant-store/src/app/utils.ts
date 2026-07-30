export class Utils {
  static getSessionObject(key: string): any {
    const raw = sessionStorage.getItem(key);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  static getSessionString(key: string): string {
    return sessionStorage.getItem(key) || '';
  }

  static getSessionNumber(key: string): number {
    const value = Number(sessionStorage.getItem(key));
    return Number.isFinite(value) ? value : 0;
  }

  static setSessionObject(key: string, value: any): void {
    sessionStorage.setItem(key, JSON.stringify(value));
  }

  static setSessionString(key: string, value: string): void {
    sessionStorage.setItem(key, value || '');
  }

  static setSessionNumber(key: string, value: number): void {
    sessionStorage.setItem(key, String(value || 0));
  }

  static clearSession(key: string): void {
    sessionStorage.removeItem(key);
  }
}

export function asArray<T>(value: any): T[] {
  if (Array.isArray(value)) {
    return value as T[];
  }
  if (value === null || value === undefined) {
    return [];
  }
  return [value as T];
}

export function toNumber(value: any): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Money is fixed-point with exactly 2 decimals. Every amount is handled as an
 * integer number of cents so that adding line totals and subtotals is exact —
 * no binary-float drift, and no currency value is ever rounded to fewer decimals.
 *
 * `toCents` maps a value that already carries 2 decimals onto its exact cent
 * count (the ×100 is a quantisation, not a loss of real precision).
 */
export function toCents(value: any): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

/** Exact integer-cent sum of raw amounts (strings or numbers). */
export function sumCents(values: Array<string | number | null | undefined>): number {
  return values.reduce<number>((total, value) => total + toCents(value), 0);
}

/** Integer cents -> "1,234.56" (2 decimals, thousands separators, no rounding). */
export function formatCents(cents: number, currency?: string): string {
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const whole = Math.trunc(abs / 100).toLocaleString(undefined);
  const frac = (abs % 100).toString().padStart(2, '0');
  const text = `${negative ? '-' : ''}${whole}.${frac}`;
  return currency ? `${currency} ${text}` : text;
}

export function formatMoney(amount: any, currency?: string): string {
  return formatCents(toCents(amount), currency);
}

export function apiErrorMessage(error: any): string {
  if (!error) {
    return 'Unknown error';
  }
  if (typeof error === 'string') {
    return error;
  }
  if (error.error) {
    if (typeof error.error === 'string') {
      return error.error;
    }
    if (error.error.error) {
      return error.error.error;
    }
    if (error.error.message) {
      return error.error.message;
    }
    if (error.error.raw) {
      return error.error.raw;
    }
  }
  if (error.message) {
    return error.message;
  }
  try {
    return JSON.stringify(error);
  } catch (_) {
    return 'Request failed';
  }
}

export function prettyJson(value: any): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch (_) {
    return String(value);
  }
}

export function parseJsonObject(text: string, label = 'JSON'): any {
  const trimmed = (text || '').trim();
  if (!trimmed) {
    return {};
  }
  try {
    return JSON.parse(trimmed);
  } catch (err: any) {
    throw new Error(`${label} is not valid JSON: ${err?.message || err}`);
  }
}

export function detailsPreview(details?: string): string {
  if (!details) {
    return '';
  }
  try {
    const parsed = JSON.parse(details);
    if (typeof parsed === 'string') {
      return parsed;
    }
    return JSON.stringify(parsed);
  } catch (_) {
    return details;
  }
}

export function isRecurringPlan(value: any): boolean {
  return !!String(value?.recurring_frequency || '').trim();
}

export function recurringCadenceLabel(value: any): string {
  if (!isRecurringPlan(value)) {
    return 'One-time purchase';
  }
  const frequency = String(value?.recurring_frequency || '').toUpperCase();
  const intervals = Math.max(1, Number(value?.recurring_intervals) || 1);
  const unit = frequency === 'WEEKLY' ? 'week' : frequency === 'YEARLY' ? 'year' : 'month';
  return `Every ${intervals} ${unit}${intervals === 1 ? '' : 's'}`;
}

export function recurringPlanLabel(value: any): string {
  if (!isRecurringPlan(value)) {
    return 'One-time purchase';
  }
  const executions = Math.max(1, Number(value?.recurring_total_execution_times) || 1);
  return `${recurringCadenceLabel(value)}, for ${executions} time${executions === 1 ? '' : 's'}`;
}

export function recurringPlannedTotal(amount: any, value: any, quantity = 1): number {
  if (!isRecurringPlan(value)) {
    return toNumber(amount) * Math.max(1, Number(quantity) || 1);
  }
  const executions = Math.max(1, Number(value?.recurring_total_execution_times) || 1);
  return toNumber(amount) * Math.max(1, Number(quantity) || 1) * executions;
}

export function nextHongKongCalendarDate(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Hong_Kong',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(new Date());
  const values: Record<string, string> = {};
  parts.forEach(part => {
    if (part.type !== 'literal') {
      values[part.type] = part.value;
    }
  });
  const date = new Date(Date.UTC(
    Number(values['year']),
    Number(values['month']) - 1,
    Number(values['day']) + 1
  ));
  return date.toISOString().slice(0, 10);
}

export function formatIsoDate(value?: string | null): string {
  if (!value) {
    return '';
  }
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return String(value);
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC'
  }).format(date);
}
