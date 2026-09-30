import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Achievement } from '../../../core/models/achievement.model';
import { AchievementService } from '../../../core/services/achievement.service';

/**
 * The student's achievements, with official (APPROVED) records shown
 * prominently and everything else demoted to a clearly-labelled secondary
 * list — a student must never mistake a pending or rejected record for an
 * official one. Nothing here is editable: official academic records are
 * authored and approved by staff.
 */
@Component({
  selector: 'app-student-achievements',
  standalone: true,
  imports: [DatePipe, RouterLink],
  template: `
    <div class="container py-4">
      <a routerLink="/student" class="small">&larr; Back to Student area</a>
      <h1 class="h4 mt-2 mb-1">My Achievements</h1>
      <p class="text-muted small">
        A verified participation does not become an achievement automatically — Faculty record one and
        your Event Coordinator approves it. Only approved achievements are official.
      </p>

      @if (errorMessage()) {
        <div class="alert alert-danger py-2 small">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <p class="text-muted small">Loading&hellip;</p>
      } @else {
        <h2 class="h6 mt-4">Official achievements</h2>
        @if (official().length === 0) {
          <p class="text-muted small">No official achievements yet.</p>
        } @else {
          <div class="row g-3">
            @for (record of official(); track record.id) {
              <div class="col-md-6">
                <div class="card border-success h-100">
                  <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                      <h3 class="h6 mb-1">{{ record.title }}</h3>
                      <span class="badge text-bg-success">Official</span>
                    </div>
                    <p class="small text-muted mb-1">
                      {{ record.achievement_type }} &middot; {{ record.achievement_date | date: 'mediumDate' }}
                    </p>
                    <p class="small text-muted mb-1">Event: {{ record.event.title }}</p>
                    @if (record.description) {
                      <p class="small mb-0">{{ record.description }}</p>
                    }
                  </div>
                </div>
              </div>
            }
          </div>
        }

        <h2 class="h6 mt-4">Not yet official</h2>
        @if (unofficial().length === 0) {
          <p class="text-muted small">Nothing pending or rejected.</p>
        } @else {
          <div class="table-responsive">
            <table class="table align-middle">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Event</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Reason (if rejected)</th>
                </tr>
              </thead>
              <tbody>
                @for (record of unofficial(); track record.id) {
                  <tr>
                    <td>{{ record.title }}</td>
                    <td class="small text-muted">{{ record.event.title }}</td>
                    <td class="small text-muted">{{ record.achievement_date | date: 'mediumDate' }}</td>
                    <td><span class="badge" [class]="badgeClass(record.status)">{{ record.status }}</span></td>
                    <td class="small">{{ record.rejection_reason || '—' }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      }
    </div>
  `,
})
export class StudentAchievementsComponent implements OnInit {
  readonly records = signal<Achievement[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  readonly official = computed(() => this.records().filter((r) => r.is_official));
  readonly unofficial = computed(() => this.records().filter((r) => !r.is_official));

  constructor(private readonly achievementService: AchievementService) {}

  ngOnInit(): void {
    this.achievementService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load your achievements.');
        this.loading.set(false);
      },
    });
  }

  badgeClass(status: string): string {
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-warning';
  }
}
