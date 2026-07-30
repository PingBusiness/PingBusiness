import { Injectable } from '@angular/core';
import { CanActivate, Router, UrlTree } from '@angular/router';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { KeycloakService } from './services/keycloak.service';

@Injectable({ providedIn: 'root' })
export class AuthGuard implements CanActivate {
  constructor(private keycloak: KeycloakService, private router: Router) {}

  canActivate(): Observable<boolean | UrlTree> {
    return this.keycloak.getValidAccessToken().pipe(
      map(token => token ? true : this.router.createUrlTree(['/signin'], {
        queryParams: { returnUrl: this.router.url || '/' }
      })),
      catchError(() => of(this.router.createUrlTree(['/signin'])))
    );
  }
}
