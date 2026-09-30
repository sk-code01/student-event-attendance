import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { DepartmentService } from '../../../core/services/department.service';
import { Department } from '../../../core/models/department.model';
import { passwordsMatchValidator } from '../../../shared/validators/password-match.validator';

const USERNAME_PATTERN = /^[a-z0-9]+$/;

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.css',
})
export class RegisterComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly departments = signal<Department[]>([]);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly fieldErrors = signal<Record<string, string>>({});
  readonly submitted = signal(false);

  readonly form = this.fb.nonNullable.group(
    {
      username: ['', [Validators.required, Validators.pattern(USERNAME_PATTERN)]],
      email: ['', [Validators.required, Validators.email]],
      full_name: ['', [Validators.required]],
      password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_password: ['', [Validators.required]],
      role: ['STUDENT', [Validators.required]],
      department: [null as number | null, [Validators.required]],
      // Required for one role each. The validator is attached and removed as
      // the role changes (see `ngOnInit`) rather than being always-on, so a
      // Faculty applicant is never blocked by a Student-only field.
      university_registration_number: [''],
      faculty_id: [''],
    },
    { validators: passwordsMatchValidator('password', 'confirm_password') },
  );

  constructor(
    private readonly authService: AuthService,
    private readonly departmentService: DepartmentService,
  ) {}

  ngOnInit(): void {
    this.departmentService.list({ all: true }).subscribe({
      next: (page) => this.departments.set(page.results),
      error: () => this.errorMessage.set('Unable to load departments. Please try again later.'),
    });

    this.applyRoleValidators(this.form.controls.role.value);
    this.form.controls.role.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((role) => this.applyRoleValidators(role));
  }

  /** Roles that are issued the college's Faculty ID. An Event Coordinator is a
   *  faculty member — the role describes what they do in this system, not a
   *  different kind of employment — so both carry the same identifier. */
  private static readonly FACULTY_ROLES = new Set(['FACULTY', 'EVENT_COORDINATOR']);

  /** The identifier a role must supply is the identifier that role is issued:
   *  a Student has a university registration number, and both faculty roles
   *  have a Faculty ID.
   *
   *  Switching role clears the identifier that no longer applies, so a stale
   *  value can never be submitted. Moving between Faculty and Event
   *  Coordinator clears nothing, because the Faculty ID still applies and
   *  making someone retype it would be a bug, not caution. */
  private applyRoleValidators(role: string): void {
    const usn = this.form.controls.university_registration_number;
    const facultyId = this.form.controls.faculty_id;
    const isFacultyRole = RegisterComponent.FACULTY_ROLES.has(role);

    usn.clearValidators();
    facultyId.clearValidators();

    if (isFacultyRole) {
      facultyId.setValidators([Validators.required]);
      usn.setValue('', { emitEvent: false });
    } else {
      usn.setValidators([Validators.required]);
      facultyId.setValue('', { emitEvent: false });
    }

    usn.updateValueAndValidity({ emitEvent: false });
    facultyId.updateValueAndValidity({ emitEvent: false });
  }

  /** Whether the currently selected role is issued a Faculty ID. Read by the
   *  template so the field and its label live in one place rather than being
   *  repeated per role. */
  readonly isFacultyRole = (role: string): boolean => RegisterComponent.FACULTY_ROLES.has(role);

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.loading.set(true);
    this.errorMessage.set(null);
    this.fieldErrors.set({});

    const raw = this.form.getRawValue();
    this.authService
      .register({
        username: raw.username,
        email: raw.email,
        full_name: raw.full_name,
        password: raw.password,
        confirm_password: raw.confirm_password,
        role: raw.role as 'STUDENT' | 'FACULTY' | 'EVENT_COORDINATOR',
        department: raw.department as number,
        // Sent only for the role that owns it: the API rejects a Student who
        // supplies a Faculty ID, and vice versa.
        ...(RegisterComponent.FACULTY_ROLES.has(raw.role)
          ? { faculty_id: raw.faculty_id }
          : { university_registration_number: raw.university_registration_number }),
      })
      .subscribe({
        next: () => {
          this.loading.set(false);
          this.submitted.set(true);
        },
        error: (error: HttpErrorResponse) => {
          this.loading.set(false);
          this.handleError(error);
        },
      });
  }

  private handleError(error: HttpErrorResponse): void {
    const body = error.error;
    if (body && typeof body === 'object') {
      const fieldErrors: Record<string, string> = {};
      for (const [key, value] of Object.entries(body)) {
        fieldErrors[key] = Array.isArray(value) ? value[0] : String(value);
      }
      this.fieldErrors.set(fieldErrors);
    }
    if (error.status === 0) {
      this.errorMessage.set('Unable to reach the server. Please check your connection.');
    } else if (!body || Object.keys(body).length === 0) {
      this.errorMessage.set('Registration failed. Please review the form and try again.');
    }
  }
}
