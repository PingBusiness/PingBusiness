import { Injectable } from '@angular/core';
import {
  HttpClient,
  HttpErrorResponse,
  HttpHeaders,
  HttpResponse
} from '@angular/common/http';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';
import {
  catchError,
  finalize,
  map,
  shareReplay,
  switchMap,
  tap,
  timeout
} from 'rxjs/operators';

import { APP_URL, AUTH_REFRESH_SKEW_MS } from '../app.configs';
import { Utils } from '../utils';


@Injectable({ providedIn: 'root' })
export class KeycloakService {
  ACCESS_TOKEN = 'ACCESS_TOKEN';
  REFRESH_TOKEN = 'REFRESH_TOKEN';
  EXPIRY = 'EXPIRY';
  REFRESH_EXPIRY = 'REFRESH_EXPIRY';

  getSessionObject = Utils.getSessionObject;
  getSessionString = Utils.getSessionString;
  getSessionNumber = Utils.getSessionNumber;

  setSessionObject = Utils.setSessionObject;
  setSessionString = Utils.setSessionString;
  setSessionNumber = Utils.setSessionNumber;

  clearSession = Utils.clearSession;

  private readonly requestTimeoutMs = 30000;
  private refreshing: Observable<string> | null = null;

  private authStateSubject = new BehaviorSubject<boolean>(this.isAuthenticated());
  authState$ = this.authStateSubject.asObservable();

  constructor(private http: HttpClient) {}

  getUser(): any {
    return this.getSessionObject('USER');
  }

  setUser(user: any): void {
    this.setSessionObject('USER', user);
  }

  isAuthenticated(): boolean {
    const accessToken = this.getSessionString(this.ACCESS_TOKEN);
    const refreshToken = this.getSessionString(this.REFRESH_TOKEN);
    if (!accessToken && !refreshToken) {
      return false;
    }
    return !this.isExpired(this.REFRESH_EXPIRY);
  }

  login(username: string, password: string): Observable<any> {
    const loginUrl = `${APP_URL}/login`;
    const json = { username, password };

    return this.http.post(loginUrl, json, { observe: 'response' }).pipe(
      switchMap((response: HttpResponse<any>) => {
        this.clearAuthenticationState(false);
        const accessToken = this.storeTokenResponse(response.body);

        const encodedUsername = encodeURIComponent(username);
        const userUrl = `${APP_URL}/user?username=${encodedUsername}`;
        const headers = new HttpHeaders({ Authorization: `Bearer ${accessToken}` });

        return this.http.get(userUrl, { headers }).pipe(
          tap((data) => {
            this.setUser(data);
            this.authStateSubject.next(true);
          }),
          catchError((error) => {
            console.error('GET request error', error);
            this.clearAuthSession();
            return throwError(() => error);
          })
        );
      })
    );
  }

  logout(): Observable<any> {
    const url = `${APP_URL}/logout`;
    const json = { refresh_token: this.getSessionString(this.REFRESH_TOKEN) };

    this.clearAuthSession();
    return this.http.post(url, json, { observe: 'response' }).pipe(
      catchError((error) => throwError(() => error))
    );
  }

  clearAuthSession(): void {
    this.clearAuthenticationState(true);
  }

  // Return a live access token. A token at/near expiry is renewed first.
  // The optional flag is additive and preserves all existing no-argument callers.
  getAccessToken(forceRefresh: boolean = false): Observable<string> {
    const accessToken = this.getSessionString(this.ACCESS_TOKEN);

    if (!forceRefresh && accessToken && !this.isExpired(this.EXPIRY)) {
      return of(accessToken);
    }

    return this.renewAccessToken();
  }

  getValidAccessToken(): Observable<string> {
    return this.getAccessToken();
  }

  get(url: string, blob?: boolean): Observable<any> {
    return this.authedRequest((accessToken) => {
      const headers = new HttpHeaders({ Authorization: `Bearer ${accessToken}` });
      const options: any = { headers };
      if (blob) {
        options.responseType = 'blob';
      }
      return this.http.get(url, options).pipe(timeout(this.requestTimeoutMs));
    }).pipe(
      catchError((error) => {
        console.error('GET request error', error);
        return throwError(() => error);
      })
    );
  }

  post(url: string, requestBody: any, responseType: 'json' | 'text' = 'json'): Observable<any> {
    return this.authedRequest((accessToken) => {
      const headers = { Authorization: `Bearer ${accessToken}` };
      const options: any = { headers };
      if (responseType === 'text') {
        options.responseType = 'text';
      }
      return this.http.post(url, requestBody, options).pipe(timeout(this.requestTimeoutMs));
    }).pipe(
      catchError((error) => {
        console.error('POST request error', error);
        return throwError(() => error);
      })
    );
  }

  delete(url: string, body?: any): Observable<any> {
    return this.authedRequest((accessToken) => {
      const headers = { Authorization: `Bearer ${accessToken}` };
      return this.http.delete(url, {
        headers,
        body: body ? body : undefined
      }).pipe(timeout(this.requestTimeoutMs));
    }).pipe(
      catchError((error) => {
        console.error('DELETE request error', error);
        return throwError(() => error);
      })
    );
  }

  private authedRequest<T>(call: (accessToken: string) => Observable<T>): Observable<T> {
    return this.getAccessToken().pipe(
      switchMap((accessToken) => call(accessToken)),
      catchError((error: any) => {
        if (!this.isUnauthorized(error) || !this.getSessionString(this.REFRESH_TOKEN)) {
          return throwError(() => error);
        }

        return this.renewAccessToken().pipe(
          switchMap((accessToken) => call(accessToken))
        );
      })
    );
  }

  private renewAccessToken(): Observable<string> {
    if (this.refreshing) {
      return this.refreshing;
    }

    const refreshToken = this.getSessionString(this.REFRESH_TOKEN);
    if (!refreshToken || this.isExpired(this.REFRESH_EXPIRY)) {
      this.clearAuthSession();
      return throwError(() => this.sessionExpiredError());
    }

    const url = `${APP_URL}/refresh`;
    const json = { refresh_token: refreshToken };

    this.refreshing = this.http.post(url, json, { observe: 'response' }).pipe(
      timeout(this.requestTimeoutMs),
      map((response: HttpResponse<any>) => {
        const accessToken = this.storeTokenResponse(response.body);
        this.authStateSubject.next(true);
        console.log('Access token renewed');
        return accessToken;
      }),
      catchError((error: any) => {
        if (this.isUnauthorizedOrForbidden(error)) {
          this.clearAuthSession();
          return throwError(() => this.sessionExpiredError());
        }

        // Preserve the stored session after network, timeout, or server errors.
        return throwError(() => error);
      }),
      finalize(() => {
        this.refreshing = null;
      }),
      shareReplay(1)
    );

    return this.refreshing;
  }

  private storeTokenResponse(body: any): string {
    const accessToken = body && body.access_token;
    if (!accessToken) {
      throw new Error('Token response did not include a usable access token');
    }

    const now = Date.now();
    this.setSessionString(this.ACCESS_TOKEN, accessToken);

    // Preserve the existing refresh token when the provider omits an unchanged one.
    if (body.refresh_token) {
      this.setSessionString(this.REFRESH_TOKEN, body.refresh_token);
    }

    if (this.isPositiveNumber(body.expires_in)) {
      this.setSessionNumber(this.EXPIRY, now + body.expires_in * 1000);
    }
    if (this.isPositiveNumber(body.refresh_expires_in)) {
      this.setSessionNumber(this.REFRESH_EXPIRY, now + body.refresh_expires_in * 1000);
    }

    return accessToken;
  }

  private isExpired(key: string): boolean {
    const expiry = this.getSessionNumber(key);
    return !!expiry && Date.now() >= expiry - AUTH_REFRESH_SKEW_MS;
  }

  private isPositiveNumber(value: any): boolean {
    return typeof value === 'number' && isFinite(value) && value > 0;
  }

  private isUnauthorized(error: any): boolean {
    return error instanceof HttpErrorResponse
      ? error.status === 401
      : error && error.status === 401;
  }

  private isUnauthorizedOrForbidden(error: any): boolean {
    const status = error instanceof HttpErrorResponse
      ? error.status
      : error && error.status;
    return status === 401 || status === 403;
  }

  private clearAuthenticationState(clearUser: boolean): void {
    this.clearSession(this.ACCESS_TOKEN);
    this.clearSession(this.REFRESH_TOKEN);
    this.clearSession(this.EXPIRY);
    this.clearSession(this.REFRESH_EXPIRY);
    if (clearUser) {
      this.clearSession('USER');
    }
    this.authStateSubject.next(false);
  }

  private sessionExpiredError(): HttpErrorResponse {
    return new HttpErrorResponse({
      status: 401,
      statusText: 'Unauthorized',
      error: { error: 'Your session has expired. Please sign in again.' }
    });
  }
}
