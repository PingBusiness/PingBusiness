import { Component } from '@angular/core';
import { Router } from '@angular/router';

import { EstoreApiService } from '../services/estore-api.service';
import { KeycloakService } from '../services/keycloak.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage } from '../utils';

// Basic email shape check: a local part, an @, a domain with a dot. Keycloak
// rejects malformed addresses server-side, but validating here gives an
// immediate, friendly error instead of a late backend failure.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

@Component({
  selector: 'app-signup',
  templateUrl: './signup.component.html',
  styleUrls: ['./signup.component.css']
})
export class SignupComponent {
  form = {
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    first_name: '',
    last_name: '',
    phone: '',
    billing_address: '',
    details: ''
  };
  loading = false;
  error = '';
  notice = '';

  get hasMinLength(): boolean {
    return this.form.password.length >= 10;
  }

  get hasNumber(): boolean {
    return /\d/.test(this.form.password);
  }

  get hasUppercase(): boolean {
    return /[A-Z]/.test(this.form.password);
  }

  constructor(
    private api: EstoreApiService,
    private keycloak: KeycloakService,
    private router: Router,
    private toast: ToastService
  ) {}

  submit(): void {
    const email = this.form.email.trim();
    if (!email) {
      this.toast.show('Email address is required.', 'error');
      return;
    }
    if (!EMAIL_RE.test(email)) {
      this.toast.show('Enter a valid email address.', 'error');
      return;
    }
    if (this.form.password !== this.form.confirmPassword) {
      this.toast.show('Passwords do not match.', 'error');
      return;
    }
    if (!this.form.phone.trim()) {
      this.toast.show('Phone number is required.', 'error');
      return;
    }
    if (!this.form.billing_address.trim()) {
      this.toast.show('Billing address is required.', 'error');
      return;
    }
    const username = (this.form.username || email).trim().toLowerCase();
    if (!username) {
      this.toast.show('Username or email is required.', 'error');
      return;
    }
    this.loading = true;
    const body = {
      username,
      email,
      password: this.form.password,
      first_name: this.form.first_name,
      last_name: this.form.last_name,
      phone: this.form.phone.trim(),
      billing_address: this.form.billing_address.trim(),
      details: this.form.details
    };
    this.api.createCustomer(body).subscribe({
      next: () => {
        this.loading = false;
        // Match the design: send the customer back to Log In with a success
        // banner rather than auto-logging them in.
        this.router.navigate(['/signin'], { queryParams: { registered: 1 } });
      },
      error: err => {
        this.loading = false;
        this.toast.show(apiErrorMessage(err), 'error');
      }
    });
  }
}
