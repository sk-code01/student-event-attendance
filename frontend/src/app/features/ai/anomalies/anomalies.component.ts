import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AnomaliesResponse, RiskLevel, RiskSignal } from '../../../core/models/ai.model';
import { AiService } from '../../../core/services/ai.service';
import { AuthService } from '../../../core/services/auth.service';
import { AiDisclaimerComponent } from '../../../shared/ai-disclaimer/ai-disclaimer.component';
import { httpErrorMessage, levelClass, reasonMessage } from '../ai-state';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

/**
 * Evidence risk signals for reviewers.
 *
 * A row is a prompt to look more closely, nothing more: there is no approve,
 * reject or dismiss control here, because the signal changes no record and
 * the only decision paths remain the existing verification screens, linked
 * per row. The level filter is client-side display filtering of rows the
 * backend already scoped and returned — it never widens anything.
 */
@Component({
  selector: 'app-anomalies',
  standalone: true,
  imports: [DecimalPipe, RouterLink, AiDisclaimerComponent, EmptyStateComponent],
  templateUrl: './anomalies.component.html',
})
export class AnomaliesComponent implements OnInit {
  private readonly aiService = inject(AiService);
  protected readonly authService = inject(AuthService);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly response = signal<AnomaliesResponse | null>(null);
  readonly levelFilter = signal<RiskLevel | 'ALL'>('ALL');

  protected readonly levelClass = levelClass;
  protected readonly LEVELS: RiskLevel[] = ['HIGH', 'MEDIUM', 'LOW'];

  readonly visibleRows = computed<RiskSignal[]>(() => {
    const rows = this.response()?.results ?? [];
    const filter = this.levelFilter();
    return filter === 'ALL' ? rows : rows.filter((row) => row.risk_level === filter);
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.aiService.anomalies().subscribe({
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

  setFilter(level: RiskLevel | 'ALL'): void {
    this.levelFilter.set(level);
  }

  unavailableMessage(response: AnomaliesResponse): string {
    return reasonMessage(response.reason, response.detail);
  }

  summaryCount(response: AnomaliesResponse, level: RiskLevel): number {
    return (response.summary as Record<string, number> | undefined)?.[level] ?? 0;
  }

  /** The existing human review screen for this row, by role. Students have
   * no review screen, so they get no link. */
  reviewLink(row: RiskSignal): string[] | null {
    if (row.evidence_id === null) {
      return null;
    }
    switch (this.authService.currentUser()?.role) {
      case 'FACULTY':
        return ['/faculty/verification', String(row.evidence_id)];
      case 'EVENT_COORDINATOR':
        return ['/event-coordinator/verification', String(row.evidence_id)];
      default:
        return null;
    }
  }

  /** True while the record still awaits a human decision. */
  isPending(row: RiskSignal): boolean {
    return row.effective_decision === 'SUBMITTED' || row.effective_decision === 'UNDER_REVIEW';
  }
}
