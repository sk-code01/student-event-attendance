import { DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Attendance } from '../../../core/models/attendance.model';
import { AttendanceService } from '../../../core/services/attendance.service';

/**
 * System-wide, read-only attendance oversight for Admin. Admin can inspect
 * every department's records (the backend queryset is unfiltered for this
 * role) but no approve/reject controls are offered here — the approval
 * authority in the UI belongs to the Event Coordinator screens. Admin retains the backend
 * capability for genuine system-wide correction; this phase deliberately does
 * not build an administrative-correction screen it was not asked for.
 */
@Component({
  selector: 'app-admin-attendance',
  standalone: true,
  imports: [DatePipe, RouterLink],
  template: `
    <div class="container py-4">
      <a routerLink="/admin" class="small">&larr; Back to Admin area</a>
      <h1 class="h4 mt-2 mb-1">Attendance (system-wide)</h1>
      <p class="text-muted small">Read-only view of every attendance record across all departments.</p>

      @if (errorMessage()) {
        <div class="alert alert-danger py-2 small">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <p class="text-muted small">Loading&hellip;</p>
      } @else if (records().length === 0) {
        <p class="text-muted small">No attendance records yet.</p>
      } @else {
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>Student</th>
                <th>Department</th>
                <th>Event</th>
                <th>Status</th>
                <th>Requested by</th>
                <th>Reviewed by</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              @for (record of records(); track record.id) {
                <tr>
                  <td>{{ record.student.username }}</td>
                  <td class="small text-muted">{{ record.student.department ?? '—' }}</td>
                  <td>
                    {{ record.event.title }}
                    <div class="small text-muted">{{ record.event.event_date | date: 'mediumDate' }}</div>
                  </td>
                  <td><span class="badge" [class]="badgeClass(record.status)">{{ record.status }}</span></td>
                  <td class="small text-muted">{{ record.requested_by?.username ?? 'Marked by coordinator' }}</td>
                  <td class="small text-muted">{{ record.reviewed_by?.username ?? '—' }}</td>
                  <td class="small">{{ record.rejection_reason || '—' }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>
  `,
})
export class AdminAttendanceComponent implements OnInit {
  readonly records = signal<Attendance[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(private readonly attendanceService: AttendanceService) {}

  ngOnInit(): void {
    this.attendanceService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load attendance records.');
        this.loading.set(false);
      },
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-info';
  }
}
