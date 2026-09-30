import { DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ODRequest } from '../../../core/models/od.model';
import { OdService } from '../../../core/services/od.service';

/** System-wide, read-only OD oversight for Admin. */
@Component({
  selector: 'app-admin-od',
  standalone: true,
  imports: [DatePipe, RouterLink],
  template: `
    <div class="container py-4">
      <a routerLink="/admin" class="small">&larr; Back to Admin area</a>
      <h1 class="h4 mt-2 mb-1">OD Requests (system-wide)</h1>
      <p class="text-muted small">
        Read-only view of every OD request across all departments. OD is tracked separately from
        attendance and neither implies the other.
      </p>

      @if (errorMessage()) {
        <div class="alert alert-danger py-2 small">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <p class="text-muted small">Loading&hellip;</p>
      } @else if (records().length === 0) {
        <p class="text-muted small">No OD requests yet.</p>
      } @else {
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>Student</th>
                <th>Department</th>
                <th>Event</th>
                <th>Reason</th>
                <th>Status</th>
                <th>Reviewed by</th>
                <th>Rejection reason</th>
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
                  <td class="small">{{ record.reason }}</td>
                  <td><span class="badge" [class]="badgeClass(record.status)">{{ record.status }}</span></td>
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
export class AdminOdComponent implements OnInit {
  readonly records = signal<ODRequest[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(private readonly odService: OdService) {}

  ngOnInit(): void {
    this.odService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load OD requests.');
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
