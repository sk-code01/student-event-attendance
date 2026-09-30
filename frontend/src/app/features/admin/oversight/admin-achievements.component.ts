import { DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Achievement } from '../../../core/models/achievement.model';
import { AchievementService } from '../../../core/services/achievement.service';

/** System-wide, read-only achievement oversight for Admin. */
@Component({
  selector: 'app-admin-achievements',
  standalone: true,
  imports: [DatePipe, RouterLink],
  template: `
    <div class="container py-4">
      <a routerLink="/admin" class="small">&larr; Back to Admin area</a>
      <h1 class="h4 mt-2 mb-1">Achievements (system-wide)</h1>
      <p class="text-muted small">
        Read-only view of every achievement record. Only records with status APPROVED are official.
      </p>

      @if (errorMessage()) {
        <div class="alert alert-danger py-2 small">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <p class="text-muted small">Loading&hellip;</p>
      } @else if (records().length === 0) {
        <p class="text-muted small">No achievements recorded yet.</p>
      } @else {
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>Student</th>
                <th>Department</th>
                <th>Achievement</th>
                <th>Event</th>
                <th>Date</th>
                <th>Status</th>
                <th>Created by</th>
                <th>Reviewed by</th>
              </tr>
            </thead>
            <tbody>
              @for (record of records(); track record.id) {
                <tr>
                  <td>{{ record.student.username }}</td>
                  <td class="small text-muted">{{ record.student.department ?? '—' }}</td>
                  <td>
                    {{ record.title }}
                    <div class="small text-muted">{{ record.achievement_type }}</div>
                  </td>
                  <td class="small text-muted">{{ record.event.title }}</td>
                  <td class="small text-muted">{{ record.achievement_date | date: 'mediumDate' }}</td>
                  <td><span class="badge" [class]="badgeClass(record.status)">{{ record.status }}</span></td>
                  <td class="small text-muted">{{ record.created_by.username }}</td>
                  <td class="small text-muted">{{ record.reviewed_by?.username ?? '—' }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>
  `,
})
export class AdminAchievementsComponent implements OnInit {
  readonly records = signal<Achievement[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(private readonly achievementService: AchievementService) {}

  ngOnInit(): void {
    this.achievementService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load achievements.');
        this.loading.set(false);
      },
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-warning';
  }
}
