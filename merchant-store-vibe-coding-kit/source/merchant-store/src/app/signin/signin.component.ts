import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { KeycloakService } from '../services/keycloak.service';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage } from '../utils';

@Component({
  selector: 'app-signin',
  templateUrl: './signin.component.html',
  styleUrls: ['./signin.component.css']
})
export class SigninComponent implements OnInit {
  username = '';
  password = '';
  loading = false;
  error = '';
  notice = '';
  noticeTitle = '';

  constructor(
    private keycloak: KeycloakService,
    private route: ActivatedRoute,
    private router: Router,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    if (this.route.snapshot.queryParamMap.get('registered')) {
      this.noticeTitle = 'Account Created';
      this.notice = 'Your account is successfully created. Please log in to continue.';
    }
  }

  onForgotPassword(): void {
    this.toast.show('Password reset isn\'t available yet — please contact the store.', 'info');
  }

  submit(): void {
    this.error = '';
    this.notice = '';
    this.loading = true;
    this.keycloak.login(this.username.trim(), this.password).subscribe({
      next: () => {
        this.loading = false;
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/catalog';
        this.router.navigateByUrl(returnUrl);
      },
      error: err => {
        this.loading = false;
        // A wrong password arrives as HTTP 400, not 401. Keycloak's token
        // endpoint answers it with {"error":"invalid_grant"} per RFC 6749
        // section 5.2, and estore-app's /login forwards Keycloak's body and
        // status verbatim. Checking only 401 therefore missed the commonest
        // failure of this form and showed the customer the raw OAuth code.
        // 401 is kept for the paths estore-app normalises itself.
        const badCredentials = err?.status === 401
          || (err?.status === 400 && err?.error?.error === 'invalid_grant');
        const message = badCredentials ? 'Invalid email or password.' : apiErrorMessage(err);
        this.error = message;
        this.toast.show(message, 'error');
      }
    });
  }
}
