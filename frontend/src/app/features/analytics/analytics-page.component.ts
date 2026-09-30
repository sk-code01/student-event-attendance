import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import {
  AchievementAnalytics,
  AnalyticsFilters,
  AnalyticsOverview,
  ApprovalAnalytics,
  DepartmentAnalytics,
  EventAnalytics,
  ParticipationAnalytics,
  TrendPeriod,
  Trends,
  VerificationAnalytics,
} from '../../core/models/analytics.model';
import { AnalyticsService } from '../../core/services/analytics.service';
import { AuthService } from '../../core/services/auth.service';
import { BarChartComponent, ChartDatum } from '../../shared/charts/bar-chart.component';
import { LineChartComponent, LineSeries } from '../../shared/charts/line-chart.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

/**
 * One analytics page for every role.
 *
 * It renders whatever the backend returns rather than switching on the role to
 * decide what to request — the server already scopes each response, so a
 * per-role client implementation would duplicate the authorization rules and
 * give a second place for them to drift.
 *
 * The one role-dependent call is the department comparison, which only Event Coordinator and
 * Admin may make; for other roles it is not requested and a 403 is treated as
 * "not available for you" rather than an error.
 *
 * No statistic is computed here. Every number, rate and trend direction comes
 * from the backend.
 */
@Component({
  selector: 'app-analytics-page',
  standalone: true,
  imports: [FormsModule, RouterLink, BarChartComponent, LineChartComponent, EmptyStateComponent],
  templateUrl: './analytics-page.component.html',
})
export class AnalyticsPageComponent implements OnInit {
  private readonly analyticsService = inject(AnalyticsService);
  protected readonly authService = inject(AuthService);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  readonly overview = signal<AnalyticsOverview | null>(null);
  readonly participation = signal<ParticipationAnalytics | null>(null);
  readonly events = signal<EventAnalytics | null>(null);
  readonly attendance = signal<ApprovalAnalytics | null>(null);
  readonly od = signal<ApprovalAnalytics | null>(null);
  readonly achievements = signal<AchievementAnalytics | null>(null);
  readonly verification = signal<VerificationAnalytics | null>(null);
  readonly trends = signal<Trends | null>(null);
  readonly departments = signal<DepartmentAnalytics | null>(null);

  dateFrom = '';
  dateTo = '';
  category = '';
  period: TrendPeriod = 'monthly';

  readonly canSeeDepartments = computed(() => {
    const role = this.authService.currentUser()?.role;
    return role === 'EVENT_COORDINATOR' || role === 'ADMIN';
  });

  ngOnInit(): void {
    this.load();
  }

  filters(): AnalyticsFilters {
    return {
      date_from: this.dateFrom || undefined,
      date_to: this.dateTo || undefined,
      category: this.category.trim() || undefined,
    };
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    const filters = this.filters();

    // A 403 on the department comparison is an expected answer for Student and
    // Faculty, not a failure — it must not blank the whole page.
    const departments$ = this.canSeeDepartments()
      ? this.analyticsService.departments(filters).pipe(catchError(() => of(null)))
      : of(null);

    forkJoin({
      overview: this.analyticsService.overview(filters),
      participation: this.analyticsService.participation(filters),
      events: this.analyticsService.events(filters),
      attendance: this.analyticsService.attendance(filters),
      od: this.analyticsService.od(filters),
      achievements: this.analyticsService.achievements(filters),
      verification: this.analyticsService.verification(filters),
      trends: this.analyticsService.trends({ ...filters, period: this.period }),
      departments: departments$,
    }).subscribe({
      next: (result) => {
        this.overview.set(result.overview);
        this.participation.set(result.participation);
        this.events.set(result.events);
        this.attendance.set(result.attendance);
        this.od.set(result.od);
        this.achievements.set(result.achievements);
        this.verification.set(result.verification);
        this.trends.set(result.trends);
        this.departments.set(result.departments);
        this.loading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.loading.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  applyFilters(): void {
    this.load();
  }

  clearFilters(): void {
    this.dateFrom = '';
    this.dateTo = '';
    this.category = '';
    this.period = 'monthly';
    this.load();
  }

  private messageFor(error: HttpErrorResponse): string {
    if (error.status === 403) {
      return 'You are not authorized to view these analytics.';
    }
    if (error.status === 400) {
      const body = error.error;
      if (body && typeof body === 'object') {
        const first = Object.values(body)[0];
        return Array.isArray(first) ? String(first[0]) : String(first);
      }
      return 'Those filters are not valid.';
    }
    if (error.status === 404) {
      return 'That event or department is not available to you.';
    }
    return 'Unable to load analytics.';
  }

  // --- chart adapters (formatting only, no statistics) --------------------

  readonly participationByEvent = computed<ChartDatum[]>(() =>
    (this.participation()?.by_event ?? []).map((row) => ({
      label: row.event_title, value: row.participations ?? 0,
    })),
  );

  readonly participationByCategory = computed<ChartDatum[]>(() =>
    (this.participation()?.by_category ?? []).map((row) => ({
      label: row.category || '(uncategorised)', value: row.participations ?? 0,
    })),
  );

  readonly achievementsByType = computed<ChartDatum[]>(() =>
    (this.achievements()?.by_type ?? []).map((row) => ({
      label: row.achievement_type || '(none)', value: row.achievements,
    })),
  );

  readonly departmentParticipation = computed<ChartDatum[]>(() =>
    (this.departments()?.departments ?? []).map((row) => ({
      label: row.department ?? '(none)', value: row.participations,
    })),
  );

  readonly trendLabels = computed(() => (this.trends()?.series ?? []).map((p) => p.period));

  readonly trendSeries = computed<LineSeries[]>(() => {
    const series = this.trends()?.series ?? [];
    return [
      { name: 'Registrations', colour: '#0d6efd', values: series.map((p) => p.registrations) },
      { name: 'Participations', colour: '#198754', values: series.map((p) => p.participations) },
      { name: 'Verified', colour: '#6f42c1', values: series.map((p) => p.verified) },
      { name: 'Attendance approved', colour: '#fd7e14', values: series.map((p) => p.attendance_approved) },
    ];
  });

  /** The trend metrics, with the wording shown to the reader. The API keys are
   * snake_case; nobody should have to read "attendance_approved" on screen. */
  readonly trendMetrics = [
    { key: 'registrations', label: 'Registrations' },
    { key: 'participations', label: 'Participations' },
    { key: 'verified', label: 'Verified' },
    { key: 'attendance_approved', label: 'Attendance approved' },
  ] as const;

  /** A rate of null means the denominator was zero — shown as an em dash so it
   * is never mistaken for 0%. */
  rate(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${value}%`;
  }

  directionLabel(metric: string): string {
    const stats = this.trends()?.statistics?.[metric];
    if (!stats || stats.direction === 'insufficient_data') {
      return 'Not enough data yet';
    }
    const pct = stats.change_percent === null ? '' : ` (${stats.change_percent}%)`;
    return `${stats.direction}${pct}`;
  }

  directionClass(metric: string): string {
    const direction = this.trends()?.statistics?.[metric]?.direction;
    if (direction === 'rising') {
      return 'text-success';
    }
    if (direction === 'falling') {
      return 'text-danger';
    }
    return 'text-muted';
  }
}
