import { DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Attendance } from '../../../core/models/attendance.model';
import { AttendanceService } from '../../../core/services/attendance.service';

/**
 * Read-only view of the student's own attendance records. There is no approve
 * control here by design — a student never approves their own attendance, and
 * the backend would refuse it regardless of what this template rendered.
 */
@Component({
  selector: 'app-student-attendance',
  standalone: true,
  imports: [DatePipe, RouterLink],
  template: `
    <div class="container py-4">
      <a routerLink="/student" class="small">&larr; Back to Student area</a>
      <h1 class="h4 mt-2 mb-1">My Attendance</h1>
      <p class="text-muted small">
        Faculty request attendance for verified participation; your Event Coordinator approves or rejects it.
        Attendance and OD are independent — one does not imply the other.
      </p>

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
                <th>Event</th>
                <th>Event date</th>
                <th>Status</th>
                <th>Requested by</th>
                <th>Reviewed</th>
                <th>Reason (if rejected)</th>
              </tr>
            </thead>
            <tbody>
              @for (record of records(); track record.id) {
                <tr>
                  <td>{{ record.event.title }}</td>
                  <td class="small text-muted">{{ record.event.event_date | date: 'mediumDate' }}</td>
                  <td><span class="badge" [class]="badgeClass(record.status)">{{ record.status }}</span></td>
                  <td class="small text-muted">{{ record.requested_by?.username ?? 'Marked by coordinator' }}</td>
                  <td class="small text-muted">
                    {{ record.reviewed_at ? (record.reviewed_at | date: 'medium') : '—' }}
                  </td>
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
export class StudentAttendanceComponent implements OnInit {
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
        this.errorMessage.set('Unable to load your attendance records.');
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
