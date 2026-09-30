import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-faculty-shell',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="page-head">
      <div class="page-head-titles">
        <h1 class="page-title">Faculty Workspace</h1>
        @if (authService.currentUser(); as user) {
          <p class="page-subtitle">
            {{ user.username }} &middot; {{ user.department?.name ?? 'No department' }}
          </p>
        }
      </div>
      <div class="page-head-actions">
        <a routerLink="/faculty/verification" class="btn btn-primary btn-sm">Open verification queue</a>
      </div>
    </div>

    <div class="section-head">
      <h2 class="section-title">Your tasks</h2>
    </div>
    <div class="grid-2">
      <a routerLink="/faculty/verification" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h3 class="card-title">Evidence verification</h3>
          <p class="card-text small mb-0">
            Review live captures and decide: verify, reject, or ask for a resubmission.
            Nothing downstream can happen until you do.
          </p>
        </div>
      </a>
      <a routerLink="/faculty/attendance-requests" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h3 class="card-title">Attendance requests</h3>
          <p class="card-text small mb-0">
            Request attendance for verified participation. The Event Coordinator approves it.
          </p>
        </div>
      </a>
      <a routerLink="/faculty/od-requests" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h3 class="card-title">On-Duty requests</h3>
          <p class="card-text small mb-0">
            A separate decision from attendance, with its own reason and its own outcome.
          </p>
        </div>
      </a>
      <a routerLink="/faculty/achievements" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h3 class="card-title">Achievements</h3>
          <p class="card-text small mb-0">
            Record a result for a verified participation. The Event Coordinator approves it before it is official.
          </p>
        </div>
      </a>
    </div>

    <div class="section">
      <div class="section-head"><h2 class="section-title">Reference</h2></div>
      <div class="page-head-actions">
        <a routerLink="/faculty/events" class="btn btn-outline-secondary btn-sm">View events</a>
        <a routerLink="/analytics" class="btn btn-outline-secondary btn-sm">Analytics</a>
        <a routerLink="/reports" class="btn btn-outline-secondary btn-sm">Reports</a>
      </div>
    </div>

    <div class="alert alert-info mt-4" role="note">
      <strong>Your authority.</strong> You verify evidence and you request attendance, OD and
      achievements. Approving them is the Event Coordinator's decision, including for records you created yourself.
    </div>
  `,
})
export class FacultyShellComponent {
  constructor(protected readonly authService: AuthService) {}
}
