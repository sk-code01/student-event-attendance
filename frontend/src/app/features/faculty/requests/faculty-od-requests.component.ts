import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { Evidence } from '../../../core/models/evidence.model';
import { ODRequest } from '../../../core/models/od.model';
import { EvidenceService } from '../../../core/services/evidence.service';
import { OdService } from '../../../core/services/od.service';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

interface Row {
  evidence: Evidence;
  odRequest: ODRequest | null;
}

/**
 * Faculty view for raising OD requests. Separate page and separate backend
 * resource from attendance — raising OD here never touches an attendance
 * record. A reason is mandatory (the Event Coordinator reviews it), so the button is
 * disabled until one is typed.
 */
@Component({
  selector: 'app-faculty-od-requests',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './faculty-od-requests.component.html',
})
export class FacultyOdRequestsComponent implements OnInit {
  readonly rows = signal<Row[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly submittingId = signal<number | null>(null);
  readonly composingId = signal<number | null>(null);
  reason = '';

  constructor(
    private readonly evidenceService: EvidenceService,
    private readonly odService: OdService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    forkJoin({ evidence: this.evidenceService.list(), od: this.odService.list() }).subscribe({
      next: ({ evidence, od }) => {
        const byParticipation = new Map(od.results.map((o) => [o.participation, o]));
        this.rows.set(
          evidence.results
            .filter((e) => e.status === 'VERIFIED')
            .map((e) => ({ evidence: e, odRequest: byParticipation.get(e.participation) ?? null })),
        );
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load verified participations.');
        this.loading.set(false);
      },
    });
  }

  startRequest(row: Row): void {
    this.composingId.set(row.evidence.id);
    this.reason = '';
    this.errorMessage.set(null);
  }

  cancelRequest(): void {
    this.composingId.set(null);
    this.reason = '';
  }

  confirmRequest(row: Row): void {
    if (!this.reason.trim() || this.submittingId() !== null) {
      return;
    }
    this.submittingId.set(row.evidence.id);
    this.odService.request(row.evidence.participation, this.reason.trim()).subscribe({
      next: (odRequest) => {
        this.submittingId.set(null);
        this.composingId.set(null);
        this.reason = '';
        this.rows.update((rows) =>
          rows.map((r) => (r.evidence.id === row.evidence.id ? { ...r, odRequest } : r)),
        );
      },
      error: (error: HttpErrorResponse) => {
        this.submittingId.set(null);
        this.errorMessage.set(this.firstError(error) ?? 'Unable to request OD.');
      },
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-info';
  }

  private firstError(error: HttpErrorResponse): string | null {
    const body = error.error;
    if (!body || typeof body !== 'object') {
      return null;
    }
    const first = Object.values(body)[0];
    return Array.isArray(first) ? String(first[0]) : String(first);
  }
}
