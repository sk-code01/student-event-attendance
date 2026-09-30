import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { DepartmentService } from '../../core/services/department.service';
import { UserAdminService } from '../../core/services/user-admin.service';
import { Department } from '../../core/models/department.model';
import { passwordsMatchValidator } from '../../shared/validators/password-match.validator';

@Component({
  selector: 'app-admin-shell',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './admin-shell.component.html',
})
export class AdminShellComponent implements OnInit {
  private readonly fb = inject(FormBuilder);

  readonly departments = signal<Department[]>([]);
  readonly loadingDepartments = signal(true);

  readonly deptSubmitting = signal(false);
  readonly deptError = signal<string | null>(null);
  readonly deptForm = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    code: ['', [Validators.required]],
  });

  readonly hodSubmitting = signal(false);
  readonly hodError = signal<Record<string, string> | null>(null);
  readonly hodSuccess = signal<string | null>(null);
  readonly eventCoordinatorForm = this.fb.nonNullable.group(
    {
      username: ['', [Validators.required, Validators.pattern(/^[a-z0-9]+$/)]],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_password: ['', [Validators.required]],
      department: [null as number | null, [Validators.required]],
    },
    { validators: passwordsMatchValidator('password', 'confirm_password') },
  );

  constructor(
    protected readonly authService: AuthService,
    private readonly departmentService: DepartmentService,
    private readonly userAdminService: UserAdminService,
  ) {}

  ngOnInit(): void {
    this.loadDepartments();
  }

  private loadDepartments(): void {
    this.loadingDepartments.set(true);
    this.departmentService.list({ all: true }).subscribe({
      next: (page) => {
        this.departments.set(page.results);
        this.loadingDepartments.set(false);
      },
      error: () => this.loadingDepartments.set(false),
    });
  }

  createDepartment(): void {
    if (this.deptForm.invalid) {
      this.deptForm.markAllAsTouched();
      return;
    }
    this.deptSubmitting.set(true);
    this.deptError.set(null);
    this.departmentService.create(this.deptForm.getRawValue()).subscribe({
      next: (dept) => {
        this.deptSubmitting.set(false);
        this.departments.update((list) => [...list, dept]);
        this.deptForm.reset();
      },
      error: (error: HttpErrorResponse) => {
        this.deptSubmitting.set(false);
        this.deptError.set(this.firstError(error) ?? 'Unable to create department.');
      },
    });
  }

  provisionEventCoordinator(): void {
    if (this.eventCoordinatorForm.invalid) {
      this.eventCoordinatorForm.markAllAsTouched();
      return;
    }
    this.hodSubmitting.set(true);
    this.hodError.set(null);
    this.hodSuccess.set(null);

    const raw = this.eventCoordinatorForm.getRawValue();
    this.userAdminService
      .provisionEventCoordinator({
        username: raw.username,
        email: raw.email,
        password: raw.password,
        confirm_password: raw.confirm_password,
        department: raw.department as number,
      })
      .subscribe({
        next: (user) => {
          this.hodSubmitting.set(false);
          this.hodSuccess.set(`Event Coordinator "${user.username}" provisioned successfully.`);
          this.eventCoordinatorForm.reset();
        },
        error: (error: HttpErrorResponse) => {
          this.hodSubmitting.set(false);
          const body = error.error;
          if (body && typeof body === 'object') {
            const fieldErrors: Record<string, string> = {};
            for (const [key, value] of Object.entries(body)) {
              fieldErrors[key] = Array.isArray(value) ? value[0] : String(value);
            }
            this.hodError.set(fieldErrors);
          }
        },
      });
  }

  private firstError(error: HttpErrorResponse): string | null {
    const body = error.error;
    if (!body || typeof body !== 'object') {
      return null;
    }
    const firstKey = Object.keys(body)[0];
    if (!firstKey) {
      return null;
    }
    const value = body[firstKey];
    return Array.isArray(value) ? value[0] : String(value);
  }
}
