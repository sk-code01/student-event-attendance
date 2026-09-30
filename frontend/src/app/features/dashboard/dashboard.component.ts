import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Dashboard } from '../../core/models/dashboard.model';
import { Role } from '../../core/models/user.model';
import { ROLE_HOME } from '../../core/navigation';
import { ROLE_LABEL } from '../../core/navigation';
import { AuthService } from '../../core/services/auth.service';
import { DashboardService } from '../../core/services/dashboard.service';
import { CountUpComponent } from '../../shared/count-up/count-up.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { DashboardAiPanelComponent } from '../ai/dashboard-panel/dashboard-ai-panel.component';

/** How each role's dashboard introduces itself. The data is identical in
 *  shape; the framing is what differs, and it matches the role's job. */
const DASHBOARD_TITLE: Record<Role, string> = {
  ADMIN: 'System Intelligence',
  EVENT_COORDINATOR: 'Department Overview',
  FACULTY: 'Your Workload',
  STUDENT: 'Your Progress',
};

/**
 * One dashboard component for all four roles.
 *
 * It renders whatever cards the backend returns rather than switching on the
 * role locally. That is deliberate: the authorization decision about what a
 * role may see lives in `apps.dashboard.services`, and duplicating it here as
 * a per-role card list would create a second place to keep in step — and a
 * tempting place to "fix" a missing card by rendering data the backend did
 * not intend to send.
 *
 * The visual identity comes from the role theme on <html>, so this component
 * has no per-role branches beyond its title and which counts it highlights.
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DatePipe, RouterLink, DashboardAiPanelComponent, CountUpComponent, EmptyStateComponent],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  protected readonly authService = inject(AuthService);

  readonly dashboard = signal<Dashboard | null>(null);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  /** Fixed-length placeholder list for the loading skeleton. */
  protected readonly skeletonSlots = [0, 1, 2, 3, 4, 5, 6, 7];

  /**
   * How many of the cards currently want attention.
   *
   * Derived from the same `isAttention` rule the cards themselves use, so the
   * hero can never disagree with what is rendered below it.
   */
  readonly attentionCount = computed(() => {
    const data = this.dashboard();
    if (!data) {
      return 0;
    }
    return data.cards.filter((card) => this.isAttention(card.key, card.value)).length;
  });

  /** Today, for the hero's dateline. Presentation only. */
  readonly today = new Date();

  /** Time-of-day greeting. Presentation only. */
  readonly greeting = computed(() => {
    const hour = new Date().getHours();
    if (hour < 12) {
      return 'Good morning';
    }
    return hour < 17 ? 'Good afternoon' : 'Good evening';
  });

  readonly roleLabel = computed(() => {
    const role = this.authService.currentUser()?.role;
    return role ? ROLE_LABEL[role] : '';
  });

  readonly dashboardTitle = computed(() => {
    const role = (this.dashboard()?.role ?? this.authService.currentUser()?.role) as Role | undefined;
    return role ? DASHBOARD_TITLE[role] : 'Dashboard';
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.dashboardService.get().subscribe({
      next: (dashboard) => {
        this.dashboard.set(dashboard);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load your dashboard.');
        this.loading.set(false);
      },
    });
  }

  /** The role's own area, used for the "my area" link. */
  homeRoute(): string {
    const role = (this.dashboard()?.role ?? this.authService.currentUser()?.role) as Role | undefined;
    return role ? ROLE_HOME[role] : '/student';
  }

  /**
   * Draws attention to queues that actually need action, and stays neutral at
   * zero so an empty dashboard never looks alarming. Replaces the old
   * `cardClass`, which returned Bootstrap border utilities; the styling now
   * comes from the design system and this only decides *whether* a card is
   * a queue that is currently non-empty.
   */
  isAttention(key: string, value: number): boolean {
    if (value === 0) {
      return false;
    }
    return key.startsWith('pending_') || key === 'attendance_pending' || key === 'od_pending';
  }
}
