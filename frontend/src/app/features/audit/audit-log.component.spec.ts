import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AuditLogComponent } from './audit-log.component';
import { ActivityRecord } from '../../core/models/activity.model';
import { ActivityService } from '../../core/services/activity.service';
import { AuthService } from '../../core/services/auth.service';

const RECORD: ActivityRecord = {
  id: 1,
  actor: { id: 2, username: 'facultycs', role: 'FACULTY', department: 'CS' },
  action: 'EVIDENCE_VERIFIED',
  description: 'Faculty recorded VERIFIED for evidence #1 version 1.',
  created_at: '2026-09-15T10:00:00Z',
};

const page = (results: ActivityRecord[], extra = {}) => ({
  results, count: results.length, next: null, previous: null, ...extra,
});

describe('AuditLogComponent', () => {
  let activityService: jasmine.SpyObj<ActivityService>;

  function configure(role = 'ADMIN') {
    activityService = jasmine.createSpyObj('ActivityService', ['auditTrail', 'myActivity']);
    TestBed.resetTestingModule();
    return TestBed.configureTestingModule({
      imports: [AuditLogComponent],
      providers: [
        provideRouter([]),
        { provide: ActivityService, useValue: activityService },
        { provide: AuthService, useValue: { currentUser: () => ({ username: 'u', role }) } },
      ],
    }).compileComponents();
  }

  it('renders audit rows for an admin', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(of(page([RECORD])));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('EVIDENCE_VERIFIED');
    expect(text).toContain('facultycs');
    expect(text).toContain('System-wide.');
  });

  it('tells an Event Coordinator their view is department-scoped', async () => {
    await configure('EVENT_COORDINATOR');
    activityService.auditTrail.and.returnValue(of(page([RECORD])));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('your department');
  });

  it('renders a system action with a null actor rather than breaking', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(of(page([{ ...RECORD, actor: null }])));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('system');
  });

  it('shows an empty state', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No audit records match');
  });

  it('surfaces a 403 as a clear forbidden message and hides the table', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(throwError(() => ({ status: 403 })));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.forbidden()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Event Coordinator and Admin accounts only');
    expect(fixture.nativeElement.querySelector('table')).toBeNull();
  });

  it('shows a generic error for other failures', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
    expect(fixture.componentInstance.forbidden()).toBeFalse();
  });

  it('passes filters to the service and resets to page 1', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(of(page([RECORD])));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.action = 'ATTENDANCE_APPROVED';
    component.search = 'participation';
    component.applyFilters();

    const args = activityService.auditTrail.calls.mostRecent().args[0] ?? {};
    expect(args.action).toBe('ATTENDANCE_APPROVED');
    expect(args.search).toBe('participation');
    expect(args.page).toBe(1);
  });

  it('clears filters', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(of(page([RECORD])));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.action = 'X';
    component.search = 'Y';
    component.clearFilters();

    expect(component.action).toBe('');
    expect(component.search).toBe('');
    const args = activityService.auditTrail.calls.mostRecent().args[0] ?? {};
    expect(args.action).toBeUndefined();
  });

  it('pages only when the backend offers a next page', async () => {
    await configure('ADMIN');
    activityService.auditTrail.and.returnValue(of(page([RECORD], { next: 'http://x/?page=2' })));
    const fixture = TestBed.createComponent(AuditLogComponent);
    fixture.detectChanges();

    fixture.componentInstance.nextPage();
    expect((activityService.auditTrail.calls.mostRecent().args[0] ?? {}).page).toBe(2);
  });
});
