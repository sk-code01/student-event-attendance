import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { EngagementResponse } from '../../../core/models/ai.model';
import { AiService } from '../../../core/services/ai.service';
import { AuthService } from '../../../core/services/auth.service';
import { AiDisclaimerComponent } from '../../../shared/ai-disclaimer/ai-disclaimer.component';
import { engagementClass, httpErrorMessage, reasonMessage } from '../ai-state';

/**
 * Engagement clusters for every role, rendered from one response.
 *
 * The backend decides what each role receives: a Student gets only their own
 * label, Faculty a department distribution, Event Coordinator/Admin also per-student rows.
 * This component renders whichever of those keys is present rather than
 * switching on the role, so the authorization rule has exactly one home.
 *
 * "HIGH" here means "groups with the most active students" — the cluster
 * order comes from the backend's centroid scoring, never from a cluster id.
 */
@Component({
  selector: 'app-engagement',
  standalone: true,
  imports: [DecimalPipe, RouterLink, AiDisclaimerComponent],
  templateUrl: './engagement.component.html',
})
export class EngagementComponent implements OnInit {
  private readonly aiService = inject(AiService);
  protected readonly authService = inject(AuthService);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly response = signal<EngagementResponse | null>(null);

  readonly isStudent = computed(() => this.authService.currentUser()?.role === 'STUDENT');

  protected readonly engagementClass = engagementClass;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.aiService.engagement().subscribe({
      next: (response) => {
        this.response.set(response);
        this.loading.set(false);
      },
      error: (error) => {
        this.errorMessage.set(httpErrorMessage(error));
        this.loading.set(false);
      },
    });
  }

  unavailableMessage(response: EngagementResponse): string {
    return reasonMessage(response.reason, response.detail);
  }

  /** Distribution entries in the backend's label order, for a stable bar. */
  distributionRows(response: EngagementResponse): { label: string; count: number; percent: number }[] {
    const distribution = response.distribution ?? {};
    const total = Object.values(distribution).reduce((sum, n) => sum + n, 0);
    const order = response.label_order ?? Object.keys(distribution);
    return order.map((label) => {
      const count = distribution[label] ?? 0;
      return { label, count, percent: total === 0 ? 0 : Math.round((count / total) * 100) };
    });
  }

  featureEntries(features: Record<string, number>): { name: string; value: number }[] {
    return Object.entries(features).map(([name, value]) => ({ name: name.replace(/_/g, ' '), value }));
  }

  /** A feature that the backend did not send renders as an em dash, never as
   * `undefined` or a made-up zero. */
  feature(features: Record<string, number>, name: string): number | string {
    return name in features ? features[name] : '—';
  }

  hasResults(response: EngagementResponse): boolean {
    return Array.isArray(response.results) && response.results.length > 0;
  }
}
