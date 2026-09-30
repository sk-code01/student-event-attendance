import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { SessionService } from '../../../core/services/session.service';
import { Role } from '../../../core/models/user.model';

const ROLE_HOME: Record<Role, string> = {
  STUDENT: '/student',
  FACULTY: '/faculty',
  EVENT_COORDINATOR: '/event-coordinator',
  ADMIN: '/admin',
};

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);

  private readonly session = inject(SessionService);

  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  /**
   * Why the user is looking at this page, when they did not come here on
   * purpose. Landing back at a login form with no explanation is the part of
   * an automatic sign-out that users find alarming, so the reason is stated.
   */
  readonly sessionNotice = computed(() => {
    switch (this.session.endReason()) {
      case 'inactivity':
        return 'Your session has expired due to inactivity. Please log in again.';
      case 'expired':
        return 'Your session is no longer valid. Please log in again.';
      case 'logged-out-elsewhere':
        return 'You were signed out in another tab. Please log in again.';
      default:
        return null;
    }
  });

  readonly form = this.fb.nonNullable.group({
    username: ['', [Validators.required]],
    password: ['', [Validators.required]],
  });

  constructor(
    private readonly authService: AuthService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
  ) {}

  submit(): void {
    // The notice describes the *previous* session; a fresh sign-in attempt
    // retires it.
    this.session.clearEndReason();

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.loading.set(true);
    this.errorMessage.set(null);

    this.authService.login(this.form.getRawValue()).subscribe({
      next: (user) => {
        this.loading.set(false);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
        this.router.navigateByUrl(returnUrl || ROLE_HOME[user.role]);
      },
      error: (error: HttpErrorResponse) => {
        this.loading.set(false);
        this.errorMessage.set(this.extractErrorMessage(error));
      },
    });
  }

  private extractErrorMessage(error: HttpErrorResponse): string {
    const body = error.error;
    if (body?.detail) {
      return Array.isArray(body.detail) ? body.detail[0] : body.detail;
    }
    if (error.status === 0) {
      return 'Unable to reach the server. Please check your connection.';
    }
    return 'Invalid username or password.';
  }
}
