import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpResponse } from '@angular/common/http';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';
import { catchError, map, timeout } from 'rxjs/operators';

import { APP_URL } from '../app.configs';
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
    const refreshExpiry = this.getSessionNumber(this.REFRESH_EXPIRY);
    if (!accessToken && !refreshToken) {
      return false;
    }
    return !refreshExpiry || Date.now() < refreshExpiry;
  }

  login(username: string, password: string): Observable<any> {
    const now = Date.now();
    const loginUrl = `${APP_URL}/login`;
    const json = { username, password };

    return new Observable((observer) => {
      this.http.post(loginUrl, json, { observe: 'response' }).subscribe({
        next: (response: HttpResponse<any>) => {
          if (response.status === 200 && response.body?.access_token) {
            this.setSessionString(this.ACCESS_TOKEN, response.body.access_token);
            this.setSessionString(this.REFRESH_TOKEN, response.body.refresh_token || '');

            // Set to 5 seconds early to avoid using a token at the exact expiry boundary.
            this.setSessionNumber(this.EXPIRY, now + ((response.body.expires_in || 0) - 5) * 1000);
            this.setSessionNumber(this.REFRESH_EXPIRY, now + ((response.body.refresh_expires_in || 0) - 5) * 1000);

            const encodedUsername = encodeURIComponent(username);
            const userUrl = `${APP_URL}/user?username=${encodedUsername}`;
            const headers = new HttpHeaders({ Authorization: `Bearer ${response.body.access_token}` });

            this.http.get(userUrl, { headers }).subscribe({
              next: (data) => {
                this.setUser(data);
                this.authStateSubject.next(true);
                observer.next(data);
                observer.complete();
              },
              error: (error) => {
                console.error('GET request error', error);
                this.clearAuthSession();
                observer.error(error);
              }
            });
          } else {
            observer.error(response.body || { error: 'Unauthorized' });
          }
        },
        error: (error) => observer.error(error)
      });
    });
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
    this.clearSession(this.ACCESS_TOKEN);
    this.clearSession(this.REFRESH_TOKEN);
    this.clearSession(this.EXPIRY);
    this.clearSession(this.REFRESH_EXPIRY);
    this.clearSession('USER');
    this.authStateSubject.next(false);
  }

  // Return access token. Automatically refresh through estore-app /refresh if already expired.
  getAccessToken(): Observable<string> {
    const now = Date.now();
    const accessToken = this.getSessionString(this.ACCESS_TOKEN);
    const refreshToken = this.getSessionString(this.REFRESH_TOKEN);
    const expiry = this.getSessionNumber(this.EXPIRY);
    const refreshExpiry = this.getSessionNumber(this.REFRESH_EXPIRY);

    if (!accessToken && !refreshToken) {
      this.clearAuthSession();
      return of('');
    }

    if (refreshExpiry && now >= refreshExpiry) {
      this.clearAuthSession();
      return of('');
    }

    if (expiry && now >= expiry && refreshToken) {
      const url = `${APP_URL}/refresh`;
      const json = { refresh_token: refreshToken };
      return this.http.post(url, json, { observe: 'response' }).pipe(
        timeout(this.requestTimeoutMs),
        map((response: any) => {
          if (response.status === 200 && response.body?.access_token) {
            this.setSessionString(this.ACCESS_TOKEN, response.body.access_token);
            if (response.body.refresh_token) {
              this.setSessionString(this.REFRESH_TOKEN, response.body.refresh_token);
            }
            this.setSessionNumber(this.EXPIRY, Date.now() + ((response.body.expires_in || 0) - 5) * 1000);
            if (response.body.refresh_expires_in) {
              this.setSessionNumber(this.REFRESH_EXPIRY, Date.now() + (response.body.refresh_expires_in - 5) * 1000);
            }
            this.authStateSubject.next(true);
            console.log('Access token renewed');
            return response.body.access_token;
          }
          this.clearAuthSession();
          return '';
        }),
        catchError((error) => {
          this.clearAuthSession();
          return throwError(() => error);
        })
      );
    }

    return of(accessToken);
  }

  getValidAccessToken(): Observable<string> {
    return this.getAccessToken();
  }

  get(url: string, blob?: boolean): Observable<any> {
    return new Observable((observer) => {
      this.getAccessToken().subscribe({
        next: (accessToken) => {
          if (!accessToken) {
            observer.error({ error: 'Not authenticated' });
            return;
          }
          const headers = new HttpHeaders({ Authorization: `Bearer ${accessToken}` });
          const options: any = { headers };
          if (blob) {
            options.responseType = 'blob';
          }

          this.http.get(url, options).pipe(timeout(this.requestTimeoutMs)).subscribe({
            next: (data) => {
              observer.next(data);
              observer.complete();
            },
            error: (error) => {
              console.error('GET request error', error);
              observer.error(error);
            }
          });
        },
        error: (error) => observer.error(error)
      });
    });
  }

  post(url: string, requestBody: any, responseType: 'json' | 'text' = 'json'): Observable<any> {
    return new Observable((observer) => {
      this.getAccessToken().subscribe({
        next: (accessToken) => {
          if (!accessToken) {
            observer.error({ error: 'Not authenticated' });
            return;
          }
          const headers = { Authorization: `Bearer ${accessToken}` };
          const options: any = { headers };
          if (responseType === 'text') {
            options.responseType = 'text';
          }

          this.http.post(url, requestBody, options).pipe(timeout(this.requestTimeoutMs)).subscribe({
            next: (data) => {
              observer.next(data);
              observer.complete();
            },
            error: (error) => {
              console.error('POST request error', error);
              observer.error(error);
            }
          });
        },
        error: (error) => observer.error(error)
      });
    });
  }

  delete(url: string, body?: any): Observable<any> {
    return new Observable((observer) => {
      this.getAccessToken().subscribe({
        next: (accessToken) => {
          if (!accessToken) {
            observer.error({ error: 'Not authenticated' });
            return;
          }
          const headers = { Authorization: `Bearer ${accessToken}` };
          this.http.delete(url, { headers, body: body ? body : undefined }).pipe(timeout(this.requestTimeoutMs)).subscribe({
            next: (data) => {
              observer.next(data);
              observer.complete();
            },
            error: (error) => {
              console.error('DELETE request error', error);
              observer.error(error);
            }
          });
        },
        error: (error) => observer.error(error)
      });
    });
  }
}
