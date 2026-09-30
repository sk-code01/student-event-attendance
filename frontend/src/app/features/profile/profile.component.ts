import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';
import { IconComponent } from '../../shared/icon/icon.component';
import { passwordsMatchValidator } from '../../shared/validators/password-match.validator';

/**
 * Account page: the signed-in user's own identity, and the password change
 * the API has always supported (`POST /users/me/password/`) but which had no
 * interface — `AuthService.changePassword` existed with nothing calling it.
 *
 * Read-only on identity by design. Username, role and department are not
 * self-service: role and department decide what a person can see and approve,
 * so they are an administrator's decision, and the username is what the audit
 * trail refers to.
 *
 * `/profile/password` deep-links here with the password section focused, so
 * the header menu's two entries are two genuine destinations rather than one
 * link and one decoration.
 */
@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule, IconComponent],
  templateUrl: './profile.component.html',
})
export class ProfileComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly toast = inject(ToastService);
  protected readonly authService = inject(AuthService);

  readonly saving = signal(false);
  readonly fieldErrors = signal<Record<string, string>>({});
  /** True when arriving at /profile/password, so the form is scrolled to. */
  readonly focusPassword = signal(false);

  readonly form = this.fb.nonNullable.group(
    {
      old_password: ['', [Validators.required]],
      new_password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_new_password: ['', [Validators.required]],
    },
    { validators: passwordsMatchValidator('new_password', 'confirm_new_password') },
  );

  ngOnInit(): void {
    // /profile/password is the header menu's "Change Password" entry. It is
    // the same page, scrolled to the form and with the first field focused —
    // so the menu item lands somewhere useful rather than at the top of a
    // page where the user has to hunt for it.
    if (this.route.snapshot.routeConfig?.path === 'profile/password') {
      this.focusPassword.set(true);
      queueMicrotask(() => {
        document.getElementById('password')?.scrollIntoView({ block: 'start' });
        document.getElementById('old-password')?.focus();
      });
    }
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.fieldErrors.set({});

    const raw = this.form.getRawValue();
    this.authService
      .changePassword({
        old_password: raw.old_password,
        new_password: raw.new_password,
        confirm_new_password: raw.confirm_new_password,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          // Cleared immediately: a password must not sit in a form after use.
          this.form.reset({ old_password: '', new_password: '', confirm_new_password: '' });
          this.toast.success('Password updated', 'Use your new password the next time you sign in.');
        },
        error: (error: HttpErrorResponse) => {
          this.saving.set(false);
          const body = error.error;
          if (body && typeof body === 'object') {
            const errors: Record<string, string> = {};
            for (const [key, value] of Object.entries(body)) {
              errors[key] = Array.isArray(value) ? String(value[0]) : String(value);
            }
            this.fieldErrors.set(errors);
          }
          this.toast.error(
            'Password not changed',
            this.firstError() ?? 'Check the details and try again.',
          );
        },
      });
  }

  protected firstError(): string | null {
    const errors = this.fieldErrors();
    const key = Object.keys(errors)[0];
    return key ? errors[key] : null;
  }

  protected readonly objectKeys = Object.keys;
}
