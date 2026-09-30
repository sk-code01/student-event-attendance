import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AnomaliesResponse, EngagementResponse, RecommendationsResponse } from '../../../core/models/ai.model';
import { AiService } from '../../../core/services/ai.service';
import { AuthService } from '../../../core/services/auth.service';
import { engagementClass, levelClass, reasonMessage } from '../ai-state';

/**
 * The dashboard's AI strip: a compact summary of each signal with a link to
 * its full page. It loads independently of the operational dashboard so an
 * AI failure can never blank the counts — each card has its own loading,
 * unavailable and error states and the rest of the page never waits on it.
 *
 * Role is consulted only to avoid requesting endpoints the backend would
 * refuse (recommendations are Student-only; risk signals are a staff view).
 */
@Component({
  selector: 'app-dashboard-ai-panel',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './dashboard-ai-panel.component.html',
})
export class DashboardAiPanelComponent implements OnInit {
  private readonly aiService = inject(AiService);
  private readonly authService = inject(AuthService);

  readonly role = computed(() => this.authService.currentUser()?.role ?? null);
  readonly isStudent = computed(() => this.role() === 'STUDENT');
  readonly isStaff = computed(() => this.role() === 'FACULTY' || this.role() === 'EVENT_COORDINATOR' || this.role() === 'ADMIN');

  readonly recommendations = signal<RecommendationsResponse | null>(null);
  readonly recommendationsError = signal(false);
  readonly engagement = signal<EngagementResponse | null>(null);
  readonly engagementError = signal(false);
  readonly anomalies = signal<AnomaliesResponse | null>(null);
  readonly anomaliesError = signal(false);

  protected readonly engagementClass = engagementClass;
  protected readonly levelClass = levelClass;
  protected readonly reasonMessage = reasonMessage;

  ngOnInit(): void {
    this.aiService.engagement().subscribe({
      next: (response) => this.engagement.set(response),
      error: () => this.engagementError.set(true),
    });
    if (this.isStudent()) {
      this.aiService.recommendations(3).subscribe({
        next: (response) => this.recommendations.set(response),
        error: () => this.recommendationsError.set(true),
      });
    }
    if (this.isStaff()) {
      this.aiService.anomalies({ limit: 5 }).subscribe({
        next: (response) => this.anomalies.set(response),
        error: () => this.anomaliesError.set(true),
      });
    }
  }

  summaryCount(response: AnomaliesResponse, level: string): number {
    return (response.summary as Record<string, number> | undefined)?.[level] ?? 0;
  }

  distributionRows(response: EngagementResponse): { label: string; count: number }[] {
    const distribution = response.distribution ?? {};
    const order = response.label_order ?? Object.keys(distribution);
    return order.map((label) => ({ label, count: distribution[label] ?? 0 }));
  }
}
