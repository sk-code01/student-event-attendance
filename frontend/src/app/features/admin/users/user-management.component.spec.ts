import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { BehaviorSubject, of, throwError } from 'rxjs';

import { UserManagementComponent } from './user-management.component';
import { AdminUser, AdminUserDetail, AdminUserStats } from '../../../core/models/admin-user.model';
import { AuthService } from '../../../core/services/auth.service';
import { DepartmentService } from '../../../core/services/department.service';
import { UserAdminService } from '../../../core/services/user-admin.service';

function row(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 2,
    username: 'studentone',
    email: 'studentone@example.com',
    full_name: '',
    role: 'STUDENT',
    university_registration_number: null,
    faculty_id: null,
    department: { id: 1, name: 'Master of Computer Applications', code: 'MCA' },
    is_active: true,
    is_staff: false,
    is_superuser: false,
    date_joined: '2026-01-01T00:00:00Z',
    last_login: null,
    ...overrides,
  };
}

function detail(overrides: Partial<AdminUserDetail> = {}): AdminUserDetail {
  return {
    ...row(),
    first_name: '',
    last_name: '',
    registration_request: null,
    ...overrides,
  };
}

const STATS: AdminUserStats = {
  total: 4,
  active: 3,
  inactive: 1,
  by_role: { STUDENT: 2, FACULTY: 1, EVENT_COORDINATOR: 0, ADMIN: 1 },
};

describe('UserManagementComponent', () => {
  let userAdmin: jasmine.SpyObj<UserAdminService>;
  let departments: jasmine.SpyObj<DepartmentService>;
  let queryParams: BehaviorSubject<Map<string, string>>;

  /** A minimal ParamMap stand-in — the component only ever calls `get`. */
  function paramMap(values: Record<string, string> = {}) {
    return { get: (key: string) => values[key] ?? null };
  }

  beforeEach(async () => {
    userAdmin = jasmine.createSpyObj('UserAdminService', [
      'list', 'stats', 'get', 'update', 'activate', 'deactivate', 'resetPassword',
    ]);
    departments = jasmine.createSpyObj('DepartmentService', ['list']);

    userAdmin.list.and.returnValue(of({ count: 1, next: null, previous: null, results: [row()] }));
    userAdmin.stats.and.returnValue(of(STATS));
    userAdmin.get.and.returnValue(of(detail()));
    departments.list.and.returnValue(
      of({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 1,
            name: 'Master of Computer Applications',
            code: 'MCA',
            is_active: true,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    );

    queryParams = new BehaviorSubject<Map<string, string>>(new Map());

    await TestBed.configureTestingModule({
      imports: [UserManagementComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: UserAdminService, useValue: userAdmin },
        { provide: DepartmentService, useValue: departments },
        {
          provide: AuthService,
          useValue: { currentUser: () => ({ id: 1, username: 'siteadmin', role: 'ADMIN', department: null }) },
        },
        {
          provide: ActivatedRoute,
          useValue: { queryParamMap: queryParams.asObservable(), snapshot: { queryParams: {} } },
        },
      ],
    }).compileComponents();
  });

  function create() {
    queryParams.next(paramMap() as never);
    const fixture = TestBed.createComponent(UserManagementComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('loads users and stats on init', () => {
    const fixture = create();
    expect(userAdmin.list).toHaveBeenCalled();
    expect(userAdmin.stats).toHaveBeenCalled();
    expect(fixture.componentInstance.users().length).toBe(1);
    expect(fixture.componentInstance.stats()?.total).toBe(4);
  });

  it('renders the user row with its authoritative fields', () => {
    const fixture = create();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('studentone');
    expect(text).toContain('studentone@example.com');
    expect(text).toContain('STUDENT');
    expect(text).toContain('MCA');
  });

  it('never renders a password or hash, because the API never sends one', () => {
    const fixture = create();
    const html: string = fixture.nativeElement.innerHTML.toLowerCase();
    expect(html).not.toContain('pbkdf2');
    expect(html).not.toContain('password_hash');
    // The only "password" text on the page is the Reset password control.
    expect(html).toContain('reset password');
  });

  it('applies the status filter arriving in the query string', () => {
    // This is what makes the dashboard "Active Users" card land on an
    // already-filtered page rather than the unfiltered list.
    queryParams.next(paramMap({ status: 'active' }) as never);
    const fixture = TestBed.createComponent(UserManagementComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.filterForm.getRawValue().status).toBe('active');
    expect(userAdmin.list).toHaveBeenCalledWith(jasmine.objectContaining({ status: 'active' }));
  });

  it('passes search, role and department filters to the API rather than filtering locally', () => {
    queryParams.next(paramMap({ search: 'ada', role: 'FACULTY', department: '1' }) as never);
    const fixture = TestBed.createComponent(UserManagementComponent);
    fixture.detectChanges();

    expect(userAdmin.list).toHaveBeenCalledWith(
      jasmine.objectContaining({ search: 'ada', role: 'FACULTY', department: '1' }),
    );
  });

  it('deactivates a user and reloads', () => {
    userAdmin.deactivate.and.returnValue(of(detail({ is_active: false })));
    const fixture = create();
    fixture.componentInstance.setActive(row(), false);

    expect(userAdmin.deactivate).toHaveBeenCalledWith(2);
    expect(fixture.componentInstance.successMessage()).toContain('inactive');
  });

  it('surfaces the backend reason when an action is refused', () => {
    // e.g. "This is the only active administrator account."
    userAdmin.deactivate.and.returnValue(
      throwError(() => ({ error: { is_active: ['This is the only active administrator account.'] } })),
    );
    const fixture = create();
    fixture.componentInstance.setActive(row(), false);

    expect(fixture.componentInstance.errorMessage()).toContain('only active administrator');
  });

  it('hides self-deactivation, which the API would refuse anyway', () => {
    const fixture = create();
    expect(fixture.componentInstance.isSelf(row({ id: 1 }))).toBeTrue();
    expect(fixture.componentInstance.isSelf(row({ id: 2 }))).toBeFalse();
  });

  it('opens the edit panel prefilled from the detail endpoint', () => {
    userAdmin.get.and.returnValue(of(detail({ email: 'a@b.com', role: 'FACULTY' })));
    const fixture = create();
    fixture.componentInstance.openEdit(row());
    fixture.detectChanges();

    const form = fixture.componentInstance.editForm.getRawValue();
    expect(form.email).toBe('a@b.com');
    expect(form.role).toBe('FACULTY');
  });

  it('reports field errors from a rejected edit', () => {
    userAdmin.update.and.returnValue(
      throwError(() => ({ error: { role: ['Department "MCA" already has an active Event Coordinator (hodmca).'] } })),
    );
    const fixture = create();
    fixture.componentInstance.openEdit(row());
    fixture.detectChanges();
    fixture.componentInstance.saveEdit();

    expect(fixture.componentInstance.panelErrors()?.['role']).toContain('already has an active Event Coordinator');
  });

  it('clears the password form after a successful reset and never echoes the password', () => {
    userAdmin.resetPassword.and.returnValue(of({ detail: 'Password updated.', sessions_revoked: 2 }));
    const fixture = create();
    fixture.componentInstance.openPasswordReset(row());
    fixture.detectChanges();
    fixture.componentInstance.passwordForm.setValue({
      new_password: 'Sup3r$ecret!',
      confirm_password: 'Sup3r$ecret!',
    });
    fixture.componentInstance.submitPasswordReset();

    expect(userAdmin.resetPassword).toHaveBeenCalled();
    expect(fixture.componentInstance.passwordForm.getRawValue().new_password).toBe('');
    expect(fixture.componentInstance.successMessage()).not.toContain('Sup3r$ecret!');
    expect(fixture.componentInstance.successMessage()).toContain('2 existing session');
  });

  it('does not submit a password reset when the confirmation does not match', () => {
    const fixture = create();
    fixture.componentInstance.openPasswordReset(row());
    fixture.componentInstance.passwordForm.setValue({
      new_password: 'Sup3r$ecret!',
      confirm_password: 'Different1!',
    });
    fixture.componentInstance.submitPasswordReset();

    expect(userAdmin.resetPassword).not.toHaveBeenCalled();
  });

  it('shows an error state when the list fails to load', () => {
    userAdmin.list.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = create();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load users');
  });

  it('computes page count from the server total, not from the rows it holds', () => {
    userAdmin.list.and.returnValue(of({ count: 45, next: 'x', previous: null, results: [row()] }));
    const fixture = create();
    expect(fixture.componentInstance.totalPages()).toBe(3);
  });
});
