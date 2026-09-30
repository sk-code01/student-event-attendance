import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { DashboardComponent } from './dashboard.component';
import { Dashboard } from '../../core/models/dashboard.model';
import { AiService } from '../../core/services/ai.service';
import { AuthService } from '../../core/services/auth.service';
import { DashboardService } from '../../core/services/dashboard.service';

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    role: 'STUDENT',
    cards: [
      { key: 'open_events', label: 'Open Events', value: 3, route: '/student/events' },
      { key: 'pending_verification', label: 'Pending Verification', value: 1, route: '/student/participation' },
    ],
    recent_activity: [],
    recent_notifications: [],
    unread_notifications: 0,
    ...overrides,
  };
}

describe('DashboardComponent', () => {
  let dashboardService: jasmine.SpyObj<DashboardService>;
  let aiService: jasmine.SpyObj<AiService>;

  beforeEach(async () => {
    dashboardService = jasmine.createSpyObj('DashboardService', ['get']);
    // The AI strip is a child with its own client; stub it so these specs
    // stay about the operational dashboard.
    aiService = jasmine.createSpyObj('AiService', ['recommendations', 'anomalies', 'engagement']);
    aiService.engagement.and.returnValue(of({ available: false, model: 'kmeans', reason: 'INSUFFICIENT_DATA',
      generated_at: '', disclaimer: '', inference_ms: 0, results: [] }));
    aiService.recommendations.and.returnValue(of({ available: false, model: 'knn', reason: 'INSUFFICIENT_DATA',
      generated_at: '', disclaimer: '', inference_ms: 0, results: [] }));
    aiService.anomalies.and.returnValue(of({ available: false, model: 'isolation_forest', reason: 'INSUFFICIENT_DATA',
      generated_at: '', disclaimer: '', inference_ms: 0, results: [] }));
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: DashboardService, useValue: dashboardService },
        { provide: AiService, useValue: aiService },
        { provide: AuthService, useValue: { currentUser: () => ({ username: 'stu', role: 'STUDENT', department: null }) } },
      ],
    }).compileComponents();
  });

  it('renders whatever cards the backend returned', () => {
    dashboardService.get.and.returnValue(of(dashboard()));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Open Events');
    expect(text).toContain('Pending Verification');
    expect(fixture.componentInstance.dashboard()?.cards.length).toBe(2);
  });

  it('calls the single role-aware endpoint, not a per-role one', () => {
    dashboardService.get.and.returnValue(of(dashboard()));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(dashboardService.get).toHaveBeenCalledTimes(1);
  });

  it('handles the zero-data state without NaN or broken cards', () => {
    dashboardService.get.and.returnValue(
      of(dashboard({ cards: [{ key: 'achievements', label: 'Achievements', value: 0, route: '/student/achievements' }] })),
    );
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('0');
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('undefined');
  });

  it('shows empty states for activity and notifications', () => {
    dashboardService.get.and.returnValue(of(dashboard()));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('No notifications');
    expect(text).toContain('No recent activity');
  });

  it('shows a message when the role has no cards at all', () => {
    dashboardService.get.and.returnValue(of(dashboard({ cards: [] })));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Nothing to show yet');
  });

  it('shows an error state when the dashboard fails to load', () => {
    dashboardService.get.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });

  it('renders the AI insight strip independently of the operational counts', () => {
    dashboardService.get.and.returnValue(of(dashboard()));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-dashboard-ai-panel')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Decision support only');
    // Counts render even though every AI signal reported itself unavailable.
    expect(fixture.nativeElement.textContent).toContain('Open Events');
  });

  it('renders the unread badge from the payload', () => {
    dashboardService.get.and.returnValue(of(dashboard({ unread_notifications: 7 })));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('7');
  });

  it('points the "my area" link at the role returned by the backend', () => {
    dashboardService.get.and.returnValue(of(dashboard({ role: 'EVENT_COORDINATOR' })));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.homeRoute()).toBe('/event-coordinator');
  });

  it('links a card to its own route, and carries query params separately', async () => {
    // Regression: the Admin "Total Users" and "Active Users" cards used to
    // link to /admin, which showed neither count. The active-users card now
    // deep-links into user management with the filter already applied, and
    // the filter travels as queryParams rather than inside the path string --
    // routerLink given "/admin/users?status=active" would encode the "?".
    dashboardService.get.and.returnValue(
      of(
        dashboard({
          role: 'ADMIN',
          cards: [
            { key: 'total_users', label: 'Total Users', value: 4, route: '/admin/users' },
            {
              key: 'active_users',
              label: 'Active Users',
              value: 3,
              route: '/admin/users',
              query: { status: 'active' },
            },
          ],
        }),
      ),
    );
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    // KPI cards are `.stat-card` in the redesigned dashboard.
    const links: HTMLAnchorElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('a.stat-card'),
    );
    const hrefs = links.map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/admin/users');
    expect(hrefs).toContain('/admin/users?status=active');
    // The "?" must be a real query separator, never percent-encoded into the path.
    expect(hrefs.some((h) => (h ?? '').includes('%3F'))).toBeFalse();
  });

  it('highlights non-empty pending queues but stays neutral at zero', () => {
    // The styling now comes from the design system; the component only
    // decides *whether* a card is a queue that currently needs attention.
    dashboardService.get.and.returnValue(of(dashboard()));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.isAttention('pending_attendance', 2)).toBeTrue();
    expect(component.isAttention('pending_attendance', 0)).toBeFalse();
    expect(component.isAttention('open_events', 5)).toBeFalse();
  });

  it('titles the dashboard for the role the backend reported', () => {
    dashboardService.get.and.returnValue(of(dashboard({ role: 'ADMIN' })));
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.dashboardTitle()).toBe('System Intelligence');
  });
});
