import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { Attendance } from '../../../core/models/attendance.model';
import { Evidence } from '../../../core/models/evidence.model';
import { AttendanceService } from '../../../core/services/attendance.service';
import { EvidenceService } from '../../../core/services/evidence.service';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

interface Row {
  evidence: Evidence;
  attendance: Attendance | null;
}

/**
 * Faculty view: verified participations eligible for an attendance request,
 * each showing whether a request already exists and where it stands.
 *
 * Eligibility is read from the evidence list's `status`, which the backend
 * keeps aligned with the effective decision (Faculty decision as possibly
 * overridden by an EVENT_COORDINATOR). The backend re-checks the effective decision from the
 * decision history when the request is actually raised, so this filter is UX
 * only and is never the security boundary.
 *
 * There is no approve/reject control anywhere in this component — Faculty
 * request, Event Coordinator decide.
 */
@Component({
  selector: 'app-faculty-attendance-requests',
  standalone: true,
  imports: [DatePipe, RouterLink, EmptyStateComponent],
  templateUrl: './faculty-attendance-requests.component.html',
})
export class FacultyAttendanceRequestsComponent implements OnInit {
  readonly rows = signal<Row[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly submittingId = signal<number | null>(null);

  constructor(
    private readonly evidenceService: EvidenceService,
    private readonly attendanceService: AttendanceService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    forkJoin({ evidence: this.evidenceService.list(), attendance: this.attendanceService.list() }).subscribe({
      next: ({ evidence, attendance }) => {
        const byParticipation = new Map(attendance.results.map((a) => [a.participation, a]));
        this.rows.set(
          evidence.results
            .filter((e) => e.status === 'VERIFIED')
            .map((e) => ({ evidence: e, attendance: byParticipation.get(e.participation) ?? null })),
        );
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load verified participations.');
        this.loading.set(false);
      },
    });
  }

  request(row: Row): void {
    if (this.submittingId() !== null || row.attendance) {
      return;
    }
    this.submittingId.set(row.evidence.id);
    this.errorMessage.set(null);
    this.attendanceService.request(row.evidence.participation).subscribe({
      next: (attendance) => {
        this.submittingId.set(null);
        this.rows.update((rows) =>
          rows.map((r) => (r.evidence.id === row.evidence.id ? { ...r, attendance } : r)),
        );
      },
      error: (error: HttpErrorResponse) => {
        this.submittingId.set(null);
        this.errorMessage.set(this.firstError(error) ?? 'Unable to request attendance.');
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
