import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { Customer, OrderItem } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { KeycloakService } from '../services/keycloak.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage, asArray, isRecurringPlan } from '../utils';

@Component({
  selector: 'app-account',
  templateUrl: './account.component.html',
  styleUrls: ['./account.component.css']
})
export class AccountComponent implements OnInit {
  profile: Customer = {};
  purchasedCount: number | null = null;
  subscriptionCount: number | null = null;

  showProfilePanel = false;
  showPasswordPanel = false;
  password = { current_password: '', new_password: '', confirm_password: '' };

  loading = false;
  saving = false;
  passwordSaving = false;

  constructor(
    private api: EstoreApiService,
    public keycloak: KeycloakService,
    private router: Router,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    forkJoin({
      profile: this.api.getCustomer().pipe(catchError(err => {
        this.toast.show(apiErrorMessage(err), 'error');
        return of({} as Customer);
      })),
      items: this.api.getOrderItems().pipe(catchError(() => of([])))
    }).subscribe(({ profile, items }) => {
      this.profile = { ...profile };
      const orderItems = asArray<OrderItem>(items);
      this.purchasedCount = orderItems.filter(item => !isRecurringPlan(item)).length;
      this.subscriptionCount = orderItems.filter(item =>
        isRecurringPlan(item) && ['ACTIVE', 'PENDING'].includes(String(item.recurring_status || '').toUpperCase())
      ).length;
      this.loading = false;
    });
  }

  toggleProfilePanel(): void {
    this.showProfilePanel = !this.showProfilePanel;
    if (this.showProfilePanel) {
      this.showPasswordPanel = false;
    }
  }

  save(): void {
    if (!this.profile.id) {
      this.toast.show('Customer profile id is missing.', 'error');
      return;
    }
    this.saving = true;
    // `details` is a backend-managed JSON field for extra customer info, not a
    // customer-editable text field — do not send it from the account form.
    this.api.updateCustomer({
      id: this.profile.id,
      first_name: this.profile.first_name,
      last_name: this.profile.last_name,
      email: this.profile.email,
      phone: this.profile.phone,
      billing_address: this.profile.billing_address
    }).subscribe({
      next: updated => {
        this.saving = false;
        if (updated && updated.id) {
          this.profile = { ...updated };
        }
        this.showProfilePanel = false;
        this.toast.show('Profile updated.', 'success');
      },
      error: err => {
        this.saving = false;
        this.toast.show(apiErrorMessage(err), 'error');
      }
    });
  }

  get pwHasMinLength(): boolean { return this.password.new_password.length >= 10; }
  get pwHasNumber(): boolean { return /\d/.test(this.password.new_password); }
  get pwHasUppercase(): boolean { return /[A-Z]/.test(this.password.new_password); }
  get pwValid(): boolean { return this.pwHasMinLength && this.pwHasNumber && this.pwHasUppercase; }

  togglePasswordPanel(): void {
    this.showPasswordPanel = !this.showPasswordPanel;
    if (this.showPasswordPanel) {
      this.showProfilePanel = false;
    } else {
      this.password = { current_password: '', new_password: '', confirm_password: '' };
    }
  }

  changePassword(): void {
    if (this.password.new_password !== this.password.confirm_password) {
      this.toast.show('New passwords do not match.', 'error');
      return;
    }
    this.passwordSaving = true;
    this.api.updatePassword(this.password.current_password, this.password.new_password).subscribe({
      next: () => {
        this.passwordSaving = false;
        this.password = { current_password: '', new_password: '', confirm_password: '' };
        this.showPasswordPanel = false;
        this.toast.show('Password updated.', 'success');
      },
      error: err => {
        this.passwordSaving = false;
        this.toast.show(apiErrorMessage(err), 'error');
      }
    });
  }

  logout(): void {
    this.keycloak.logout().subscribe({
      next: () => this.router.navigate(['/signin']),
      error: () => this.router.navigate(['/signin'])
    });
  }
}
