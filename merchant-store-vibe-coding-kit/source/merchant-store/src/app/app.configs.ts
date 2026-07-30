/**
 * Runtime deployment configuration.
 *
 * The container writes /assets/runtime-config.js when it starts. Loading the
 * configuration at runtime means the same tested Angular image can be deployed
 * behind different merchant domains without rebuilding it.
 */
export interface PingBusinessRuntimeConfig {
  apiUrl?: string;
}

declare global {
  interface Window {
    __PINGBUSINESS_CONFIG__?: PingBusinessRuntimeConfig;
  }
}

function normalizedApiUrl(value: unknown): string {
  if (typeof value !== 'string') {
    return '';
  }
  return value.trim().replace(/\/+$/, '');
}

const runtimeApiUrl = normalizedApiUrl(window.__PINGBUSINESS_CONFIG__?.apiUrl);

// Used by `ng serve` and local builds. Production containers require
// ESTORE_APP_PUBLIC_URL and replace the runtime file during startup.
export const APP_URL = runtimeApiUrl || 'http://localhost:5000';

export const EXPIRY_MS = 60 * 60 * 1000;
export const MIN_PASSWORD_LENGTH = 10;
export const AUTH_REFRESH_SKEW_MS = 5 * 1000;
