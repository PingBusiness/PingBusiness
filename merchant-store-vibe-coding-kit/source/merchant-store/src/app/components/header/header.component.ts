import { Component, OnInit } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { of } from 'rxjs';
import { catchError, filter } from 'rxjs/operators';

import { CartService } from '../../services/cart.service';
import { KeycloakService } from '../../services/keycloak.service';
import { EstoreApiService } from '../../services/estore-api.service';

@Component({
  selector: 'app-header',
  templateUrl: './header.component.html',
  styleUrls: ['./header.component.css']
})
export class HeaderComponent implements OnInit {
  menuOpen = false;
  // API-driven only: starts empty and is set from the store API below. Do NOT
  // seed this with a hardcoded name or fallback constant — a literal here would
  // flash on every reload before the real store name loads.
  storeName = '';
  isHome = false;
  cartCount$ = this.cart.count$;
  authState$ = this.keycloak.authState$;

  constructor(
    private router: Router,
    private cart: CartService,
    private keycloak: KeycloakService,
    private api: EstoreApiService
  ) {}

  ngOnInit(): void {
    // The header floats over the hero on Home only (presentation-only route
    // awareness); every other route keeps the standard in-flow header.
    this.isHome = this.checkHome(this.router.url);
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd)
    ).subscribe(event => this.isHome = this.checkHome(event.urlAfterRedirects));

    this.api.getStore().pipe(catchError(() => of(undefined))).subscribe(store => {
      if (store?.name) {
        this.storeName = store.name;
      }
    });
  }

  private checkHome(url: string): boolean {
    return (url || '').split('?')[0].split('#')[0] === '/';
  }

  logout(): void {
    this.menuOpen = false;
    this.keycloak.logout().subscribe({
      next: () => this.router.navigate(['/signin']),
      error: () => this.router.navigate(['/signin'])
    });
  }
}
