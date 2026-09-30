import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AnalyticsPageComponent } from './analytics-page.component';
import {
  AchievementAnalytics,
  AnalyticsOverview,
  ApprovalAnalytics,
  DepartmentAnalytics,
  EventAnalytics,
  ParticipationAnalytics,
  RegistrationAnalytics,
  Trends,
  VerificationAnalytics,
} from '../../core/models/analytics.model';
import { AnalyticsService } from '../../core/services/analytics.service';
import { AuthService } from '../../core/services/auth.service';

function overview(extra: Partial<AnalyticsOverview> = {}): AnalyticsOverview {
  return {
    events: 2, registrations: 3, live_registrations: 2, participations: 2,
    evidence_submitted: 2, verified_participations: 1, pending_verification: 0,
    attendance_requests: 1, attendance_approved: 1, od_requests: 1, od_approved: 1,
    achievements: 1, official_achievements: 1,
    participation_rate: 100.0,
    participation_rate_basis: 'participations / live registrations',
    ...extra,
  };
}

const EMPTY_APPROVAL: ApprovalAnalytics = {
  total_requests: 0, pending: 0, approved: 0, rejected: 0,
  approval_rate: null, approval_rate_basis: 'approved / decided', by_event: [],
};

function stubService(overrides: Record<string, unknown> = {}) {
  const spy = jasmine.createSpyObj<AnalyticsService>('AnalyticsService', [
    'overview', 'participation', 'events', 'registrations', 'attendance', 'od',
    'achievements', 'verification', 'trends', 'departments',
  ]);
  spy.overview.and.returnValue(of(overview()));
  spy.participation.and.returnValue(of({
    total_registrations: 3, live_registrations: 2, total_participations: 2,
    submitted_participations: 2, draft_participations: 0, verified_participations: 1,
    pending_verification: 0, rejected_evidence: 1, resubmission_required: 0,
    participation_rate: 100, participation_rate_basis: 'basis',
    verification_success_rate: 50, verification_success_rate_basis: 'basis',
    by_event: [{ event_id: 1, event_title: 'CS Event', participations: 2 }],
    by_category: [{ category: 'Technical', participations: 2 }],
  } as ParticipationAnalytics));
  spy.events.and.returnValue(of({
    total_events: 2, draft_events: 0, published_events: 1, cancelled_events: 1,
    completed_events: 0, by_category: [],
    per_event: [{
      id: 1, title: 'CS Event', event_date: '2026-09-15', category: 'Technical',
      status: 'PUBLISHED', registrations: 2, participations: 2,
    }],
  } as EventAnalytics));
  spy.registrations.and.returnValue(of({
    total_registrations: 3, live_registrations: 2, cancelled_registrations: 1,
    cancellation_rate: 33.33, cancellation_rate_basis: 'basis', by_event: [],
  } as RegistrationAnalytics));
  spy.attendance.and.returnValue(of({ ...EMPTY_APPROVAL, total_requests: 1, approved: 1, approval_rate: 100 }));
  spy.od.and.returnValue(of(EMPTY_APPROVAL));
  spy.achievements.and.returnValue(of({
    total_achievements: 2, draft: 0, pending_approval: 1, official_achievements: 1,
    rejected: 0, approval_rate: 100, approval_rate_basis: 'basis',
    by_type: [{ achievement_type: 'Competition', achievements: 2, approved: 1 }], by_event: [],
  } as AchievementAnalytics));
  spy.verification.and.returnValue(of({
    total_evidence: 2, pending_review: 0, verified: 1, rejected: 1, resubmission_required: 0,
    event_coordinator_overrides: 1, verification_rate: 50, verification_rate_basis: 'basis',
    decision_basis: 'effective decision (Event Coordinator override takes precedence)', by_event: [],
  } as VerificationAnalytics));
  spy.trends.and.returnValue(of({
    period: 'monthly', timezone: 'Asia/Kolkata',
    series: [
      { period: '2026-08', registrations: 1, participations: 1, verified: 0, attendance_approved: 0, od_approved: 0, achievements: 0 },
      { period: '2026-09', registrations: 3, participations: 2, verified: 1, attendance_approved: 1, od_approved: 1, achievements: 1 },
    ],
    statistics: {
      registrations: {
        total: 4, periods: 2, average: 2, latest: 3, previous: 1, change: 2,
        change_percent: 200, direction: 'rising', moving_average_3: [],
      },
      participations: {
        total: 3, periods: 2, average: 1.5, latest: 2, previous: 1, change: 1,
        change_percent: 100, direction: 'rising', moving_average_3: [],
      },
      verified: {
        total: 1, periods: 2, average: 0.5, latest: 1, previous: 0, change: 1,
        change_percent: null, direction: 'rising', moving_average_3: [],
      },
      attendance_approved: {
        total: 1, periods: 2, average: 0.5, latest: 1, previous: 0, change: 1,
        change_percent: null, direction: 'rising', moving_average_3: [],
      },
    },
  } as Trends));
  spy.departments.and.returnValue(of({
    departments: [{
      department_id: 1, department: 'Computer Science', events: 2, registrations: 3,
      participations: 2, attendance_approved: 1, od_approved: 1, official_achievements: 1,
    }],
    department_less_events: 1,
    department_less_note: 'Admin-created events belong to no department.',
  } as DepartmentAnalytics));
  Object.assign(spy, overrides);
  return spy;
}

async function configure(role: string, service: jasmine.SpyObj<AnalyticsService>) {
  TestBed.resetTestingModule();
  await TestBed.configureTestingModule({
    imports: [AnalyticsPageComponent],
    providers: [
      provideRouter([]),
      { provide: AnalyticsService, useValue: service },
      { provide: AuthService, useValue: { currentUser: () => ({ username: 'u', role, department: null }) } },
    ],
  }).compileComponents();
}

describe('AnalyticsPageComponent', () => {
  it('renders headline counts from the backend', async () => {
    const service = stubService();
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Participations');
    expect(text).toContain('100%');
    expect(fixture.componentInstance.overview()?.participations).toBe(2);
  });

  it('does not request department analytics for a Student', async () => {
    const service = stubService();
    await configure('STUDENT', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    expect(service.departments).not.toHaveBeenCalled();
    expect(fixture.componentInstance.canSeeDepartments()).toBeFalse();
  });

  it('does not request department analytics for Faculty', async () => {
    const service = stubService();
    await configure('FACULTY', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();
    expect(service.departments).not.toHaveBeenCalled();
  });

  it('requests and renders department analytics for Event Coordinator and Admin', async () => {
    const service = stubService();
    await configure('ADMIN', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    expect(service.departments).toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Participations by department');
  });

  it('keeps the page usable when the department call is forbidden', async () => {
    const service = stubService();
    service.departments.and.returnValue(throwError(() => ({ status: 403 })));
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.errorMessage()).toBeNull();
    expect(fixture.componentInstance.overview()).not.toBeNull();
    expect(fixture.componentInstance.departments()).toBeNull();
  });

  it('passes filters to every request', async () => {
    const service = stubService();
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.dateFrom = '2026-09-01';
    component.category = 'Technical';
    component.period = 'daily';
    component.applyFilters();

    expect(service.overview).toHaveBeenCalledWith(
      jasmine.objectContaining({ date_from: '2026-09-01', category: 'Technical' }),
    );
    expect(service.trends).toHaveBeenCalledWith(jasmine.objectContaining({ period: 'daily' }));
  });

  it('clears filters back to defaults', async () => {
    const service = stubService();
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.dateFrom = '2026-09-01';
    component.category = 'X';
    component.clearFilters();

    expect(component.dateFrom).toBe('');
    expect(component.category).toBe('');
    expect(component.period).toBe('monthly');
  });

  it('shows a null rate as an em dash, never as 0%', async () => {
    const service = stubService();
    service.overview.and.returnValue(of(overview({ participation_rate: null })));
    await configure('STUDENT', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.rate(null)).toBe('—');
    expect(fixture.nativeElement.textContent).toContain('—');
  });

  it('renders an empty state instead of crashing on empty analytics', async () => {
    const service = stubService();
    service.participation.and.returnValue(of({
      total_registrations: 0, live_registrations: 0, total_participations: 0,
      submitted_participations: 0, draft_participations: 0, verified_participations: 0,
      pending_verification: 0, rejected_evidence: 0, resubmission_required: 0,
      participation_rate: null, participation_rate_basis: 'b',
      verification_success_rate: null, verification_success_rate_basis: 'b',
      by_event: [], by_category: [],
    } as ParticipationAnalytics));
    service.trends.and.returnValue(of({
      period: 'monthly', timezone: 'Asia/Kolkata', series: [], statistics: {},
    } as Trends));
    await configure('STUDENT', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('No participations yet.');
    expect(text).toContain('No activity in this period.');
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('undefined');
  });

  it('reports a validation error from the backend', async () => {
    const service = stubService();
    service.overview.and.returnValue(
      throwError(() => ({ status: 400, error: { date_from: ['Expected an ISO date.'] } })),
    );
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Expected an ISO date.');
  });

  it('reports an authorization failure clearly', async () => {
    const service = stubService();
    service.overview.and.returnValue(throwError(() => ({ status: 403 })));
    await configure('STUDENT', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('not authorized');
  });

  it('reports a generic failure', async () => {
    const service = stubService();
    service.overview.and.returnValue(throwError(() => ({ status: 500 })));
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });

  it('labels trend direction from backend statistics only', async () => {
    const service = stubService();
    await configure('EVENT_COORDINATOR', service);
    const fixture = TestBed.createComponent(AnalyticsPageComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.directionLabel('registrations')).toContain('rising');
    expect(component.directionLabel('registrations')).toContain('200%');
    expect(component.directionClass('registrations')).toContain('success');
    // change_percent null must not render "null%"
    expect(component.directionLabel('verified')).toBe('rising');
    expect(component.directionLabel('nonexistent')).toContain('Not enough data');
  });
});
