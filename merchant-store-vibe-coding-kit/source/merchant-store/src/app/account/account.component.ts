import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { Customer, OrderItem } from '../app.types';
import { EstoreApiService } from '../services/estore-api.service';
import { KeycloakService } from '../services/keycloak.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage, asArray, isRecurringPlan } from '../utils';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

@Component({
  selector: 'app-account',
  templateUrl: './account.component.html',
  styleUrls: ['./account.component.css']
})
export class AccountComponent implements OnInit {
  profile: Customer = {};
  // The Edit Profile form binds to this copy, never to `profile` itself, so an
  // abandoned edit cannot leak into the card behind the modal.
  draft: Customer = {};
  profileSubmitted = false;
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
    if (this.showProfilePanel) {
      this.closeProfilePanel();
      return;
    }
    // Open on a snapshot. The form used to bind straight to `profile`, so every
    // keystroke rewrote the card behind the modal and Cancel looked like it had
    // saved. The draft is promoted to `profile` only once the API confirms.
    this.draft = { ...this.profile };
    this.profileSubmitted = false;
    this.showProfilePanel = true;
    this.showPasswordPanel = false;
  }

  private closeProfilePanel(): void {
    this.showProfilePanel = false;
    this.draft = {};
    this.profileSubmitted = false;
  }

  private isBlank(value?: string | null): boolean {
    return !String(value ?? '').trim();
  }

  get firstNameError(): string {
    return this.profileSubmitted && this.isBlank(this.draft.first_name) ? 'First name is required.' : '';
  }

  get lastNameError(): string {
    return this.profileSubmitted && this.isBlank(this.draft.last_name) ? 'Last name is required.' : '';
  }

  get emailError(): string {
    if (!this.profileSubmitted) {
      return '';
    }
    const email = String(this.draft.email ?? '').trim();
    if (!email) {
      return 'Email is required.';
    }
    return EMAIL_PATTERN.test(email) ? '' : 'Enter a valid email address.';
  }

  get profileValid(): boolean {
    const email = String(this.draft.email ?? '').trim();
    return !this.isBlank(this.draft.first_name)
      && !this.isBlank(this.draft.last_name)
      && EMAIL_PATTERN.test(email);
  }

  save(): void {
    if (!this.profile.id) {
      this.toast.show('Customer profile id is missing.', 'error');
      return;
    }
    // Surface the messages only once the customer has tried to save, then stop
    // here rather than sending blank identity fields to the API.
    this.profileSubmitted = true;
    if (!this.profileValid) {
      return;
    }
    // `details` is a backend-managed JSON field for extra customer info, not a
    // customer-editable text field — do not send it from the account form.
    const payload = {
      id: this.profile.id,
      first_name: String(this.draft.first_name ?? '').trim(),
      last_name: String(this.draft.last_name ?? '').trim(),
      email: String(this.draft.email ?? '').trim(),
      phone: String(this.draft.phone ?? '').trim(),
      billing_address: String(this.draft.billing_address ?? '').trim()
    };
    this.saving = true;
    this.api.updateCustomer(payload).subscribe({
      next: updated => {
        this.saving = false;
        this.profile = updated && updated.id ? { ...updated } : { ...this.profile, ...payload };
        this.closeProfilePanel();
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
