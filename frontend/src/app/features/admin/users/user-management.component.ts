import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  AdminUser,
  AdminUserDetail,
  AdminUserStats,
} from '../../../core/models/admin-user.model';
import { Department } from '../../../core/models/department.model';
import { Role } from '../../../core/models/user.model';
import { AuthService } from '../../../core/services/auth.service';
import { DepartmentService } from '../../../core/services/department.service';
import { UserAdminService } from '../../../core/services/user-admin.service';
import { passwordsMatchValidator } from '../../../shared/validators/password-match.validator';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';
import { CountUpComponent } from '../../../shared/count-up/count-up.component';

type Panel = 'none' | 'detail' | 'edit' | 'password';

const PAGE_SIZE = 20;

/**
 * Admin user management.
 *
 * Filtering, searching and paging all happen on the server — this component
 * never holds the full user list and never filters in the browser, so the
 * page costs the same whether the institution has forty accounts or four
 * thousand.
 *
 * The filter state is mirrored into the URL query string, which is what lets
 * the dashboard's "Active Users" card link straight to
 * `/admin/users?status=active` and land on an already-filtered page. It also
 * means a filtered view can be bookmarked or shared between administrators.
 *
 * Authorization is the API's job. The route guard here keeps the link out of
 * other roles' navigation; every endpoint this component calls independently
 * refuses a non-Admin with 403.
 */
@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, EmptyStateComponent, CountUpComponent],
  templateUrl: './user-management.component.html',
})
export class UserManagementComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly userAdmin = inject(UserAdminService);
  private readonly departmentService = inject(DepartmentService);
  protected readonly authService = inject(AuthService);

  readonly users = signal<AdminUser[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly stats = signal<AdminUserStats | null>(null);
  readonly departments = signal<Department[]>([]);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  readonly panel = signal<Panel>('none');
  readonly selected = signal<AdminUserDetail | null>(null);
  readonly panelBusy = signal(false);
  readonly panelErrors = signal<Record<string, string> | null>(null);

  /** Which row has an action in flight, so only that row's buttons disable. */
  readonly rowBusyId = signal<number | null>(null);

  readonly roles: Role[] = ['STUDENT', 'FACULTY', 'EVENT_COORDINATOR', 'ADMIN'];

  readonly filterForm = this.fb.nonNullable.group({
    search: [''],
    role: [''],
    department: [''],
    status: ['all'],
  });

  readonly editForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    first_name: [''],
    last_name: [''],
    role: ['STUDENT' as Role, [Validators.required]],
    department: ['' as string],
  });

  readonly passwordForm = this.fb.nonNullable.group(
    {
      new_password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_password: ['', [Validators.required]],
    },
    { validators: passwordsMatchValidator('new_password', 'confirm_password') },
  );

  ngOnInit(): void {
    this.loadDepartments();
    // Seed the filters from the query string so a deep link such as
    // /admin/users?status=active arrives already filtered.
    //
    // `queryParamMap` never completes, so the subscription must be torn down
    // with the component; without this, navigating away and back would leave
    // a live subscription behind on every visit.
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      this.filterForm.patchValue(
        {
          search: params.get('search') ?? '',
          role: params.get('role') ?? '',
          department: params.get('department') ?? '',
          status: params.get('status') ?? 'all',
        },
        { emitEvent: false },
      );
      this.page.set(Number(params.get('page')) || 1);
      this.load();
    });
  }

  // ----------------------------------------------------------------- data

  private loadDepartments(): void {
    this.departmentService.list({ all: true }).subscribe({
      next: (page) => this.departments.set(page.results),
      error: () => this.departments.set([]),
    });
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    const filters = this.filterForm.getRawValue();

    this.userAdmin
      .list({
        search: filters.search,
        role: filters.role,
        department: filters.department,
        status: filters.status as 'active' | 'inactive' | 'all',
        page: this.page(),
      })
      .subscribe({
        next: (result) => {
          this.users.set(result.results);
          this.total.set(result.count);
          this.loading.set(false);
        },
        error: () => {
          this.errorMessage.set('Unable to load users.');
          this.loading.set(false);
        },
      });

    this.userAdmin.stats().subscribe({
      next: (stats) => this.stats.set(stats),
      error: () => this.stats.set(null),
    });
  }

  /** Pushes the filter state into the URL; the queryParamMap subscription
   * above then reloads. One code path for "filters changed", whether the
   * change came from the form or from a link. */
  applyFilters(page = 1): void {
    const filters = this.filterForm.getRawValue();
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        search: filters.search || null,
        role: filters.role || null,
        department: filters.department || null,
        status: filters.status === 'all' ? null : filters.status,
        page: page > 1 ? page : null,
      },
      queryParamsHandling: 'merge',
    });
  }

  resetFilters(): void {
    this.filterForm.reset({ search: '', role: '', department: '', status: 'all' });
    this.applyFilters();
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) {
      return;
    }
    this.applyFilters(page);
  }

  totalPages(): number {
    return Math.max(1, Math.ceil(this.total() / PAGE_SIZE));
  }

  // --------------------------------------------------------------- panels

  openDetail(user: AdminUser): void {
    this.openPanel('detail', user.id);
  }

  openEdit(user: AdminUser): void {
    this.openPanel('edit', user.id);
  }

  openPasswordReset(user: AdminUser): void {
    this.passwordForm.reset({ new_password: '', confirm_password: '' });
    this.openPanel('password', user.id);
  }

  private openPanel(panel: Panel, id: number): void {
    this.panelErrors.set(null);
    this.successMessage.set(null);
    this.panelBusy.set(true);
    this.panel.set(panel);
    this.userAdmin.get(id).subscribe({
      next: (user) => {
        this.selected.set(user);
        this.panelBusy.set(false);
        if (panel === 'edit') {
          this.editForm.reset({
            email: user.email,
            first_name: user.first_name ?? '',
            last_name: user.last_name ?? '',
            role: user.role,
            department: user.department ? String(user.department.id) : '',
          });
        }
      },
      error: () => {
        this.panelBusy.set(false);
        this.closePanel();
        this.errorMessage.set('Unable to load that user.');
      },
    });
  }

  closePanel(): void {
    this.panel.set('none');
    this.selected.set(null);
    this.panelErrors.set(null);
  }

  // --------------------------------------------------------------- actions

  saveEdit(): void {
    const user = this.selected();
    if (!user || this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      return;
    }
    const raw = this.editForm.getRawValue();
    this.panelBusy.set(true);
    this.panelErrors.set(null);

    this.userAdmin
      .update(user.id, {
        email: raw.email,
        first_name: raw.first_name,
        last_name: raw.last_name,
        role: raw.role,
        department: raw.department ? Number(raw.department) : null,
      })
      .subscribe({
        next: (updated) => {
          this.panelBusy.set(false);
          this.successMessage.set(`Saved changes to "${updated.username}".`);
          this.closePanel();
          this.load();
        },
        error: (error: HttpErrorResponse) => {
          this.panelBusy.set(false);
          this.panelErrors.set(this.fieldErrors(error));
        },
      });
  }

  setActive(user: AdminUser, active: boolean): void {
    this.rowBusyId.set(user.id);
    this.errorMessage.set(null);
    this.successMessage.set(null);

    const request = active ? this.userAdmin.activate(user.id) : this.userAdmin.deactivate(user.id);
    request.subscribe({
      next: () => {
        this.rowBusyId.set(null);
        this.successMessage.set(
          `"${user.username}" is now ${active ? 'active' : 'inactive'}.`,
        );
        this.load();
      },
      error: (error: HttpErrorResponse) => {
        this.rowBusyId.set(null);
        // The backend refuses, for example, deactivating the last Admin or
        // activating a second Event Coordinator for a department. Show its reason verbatim
        // rather than a generic failure.
        this.errorMessage.set(this.firstError(error) ?? 'Unable to change that account.');
      },
    });
  }

  submitPasswordReset(): void {
    const user = this.selected();
    if (!user || this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    this.panelBusy.set(true);
    this.panelErrors.set(null);

    this.userAdmin.resetPassword(user.id, this.passwordForm.getRawValue()).subscribe({
      next: (result) => {
        this.panelBusy.set(false);
        // The password is cleared from the form immediately and is never
        // shown back; the only confirmation is that it worked.
        this.passwordForm.reset({ new_password: '', confirm_password: '' });
        this.successMessage.set(
          `Password updated for "${user.username}". `
          + `${result.sessions_revoked} existing session(s) were signed out.`,
        );
        this.closePanel();
      },
      error: (error: HttpErrorResponse) => {
        this.panelBusy.set(false);
        this.panelErrors.set(this.fieldErrors(error));
      },
    });
  }

  // ---------------------------------------------------------------- helpers

  /** True when the acting Admin is looking at their own row — used to hide
   * the self-deactivate button the API would refuse anyway. */
  isSelf(user: AdminUser): boolean {
    return this.authService.currentUser()?.id === user.id;
  }

  roleBadgeClass(role: Role): string {
    switch (role) {
      case 'ADMIN':
        return 'text-bg-dark';
      case 'EVENT_COORDINATOR':
        return 'text-bg-primary';
      case 'FACULTY':
        return 'text-bg-info';
      default:
        return 'text-bg-secondary';
    }
  }

  private fieldErrors(error: HttpErrorResponse): Record<string, string> {
    const body = error.error;
    if (!body || typeof body !== 'object') {
      return { detail: 'Request failed. Please try again.' };
    }
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(body)) {
      result[key] = Array.isArray(value) ? String(value[0]) : String(value);
    }
    return result;
  }

  private firstError(error: HttpErrorResponse): string | null {
    const errors = this.fieldErrors(error);
    const firstKey = Object.keys(errors)[0];
    return firstKey ? errors[firstKey] : null;
  }

  protected readonly objectKeys = Object.keys;
}
