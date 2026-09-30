import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-student-shell',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="page-head">
      <div class="page-head-titles">
        <h1 class="page-title">Student Experience Hub</h1>
        @if (authService.currentUser(); as user) {
          <p class="page-subtitle">
            Welcome back, {{ user.username }} &middot; {{ user.department?.name ?? 'No department' }}
          </p>
        }
      </div>
      <div class="page-head-actions">
        <a routerLink="/student/events" class="btn btn-primary btn-sm">Browse Events</a>
        <a routerLink="/recommendations" class="btn btn-outline-primary btn-sm">Recommended for You</a>
      </div>
    </div>

    <div class="grid-3">
      <a routerLink="/student/events" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h2 class="card-title">Discover events</h2>
          <p class="card-text small mb-0">
            Browse what is open for registration and sign up.
          </p>
        </div>
      </a>
      <a routerLink="/student/registrations" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h2 class="card-title">My registrations</h2>
          <p class="card-text small mb-0">
            Events you have signed up for, and the ones you can still cancel.
          </p>
        </div>
      </a>
      <a routerLink="/student/participation" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h2 class="card-title">My participation</h2>
          <p class="card-text small mb-0">
            Your captured evidence and where each submission stands.
          </p>
        </div>
      </a>
      <a routerLink="/student/attendance" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h2 class="card-title">My attendance</h2>
          <p class="card-text small mb-0">Attendance your Event Coordinator has decided on.</p>
        </div>
      </a>
      <a routerLink="/student/od" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h2 class="card-title">My OD requests</h2>
          <p class="card-text small mb-0">On-Duty decisions, separate from attendance.</p>
        </div>
      </a>
      <a routerLink="/student/achievements" class="card is-interactive text-decoration-none">
        <div class="card-body">
          <h2 class="card-title">My achievements</h2>
          <p class="card-text small mb-0">Only approved records are official.</p>
        </div>
      </a>
    </div>

    <div class="alert alert-info mt-4" role="note">
      <strong>How this works.</strong> Registering for an event is not the same as taking part in it;
      capturing evidence is not the same as being marked present; and being marked present is not an
      achievement. Each one is a separate decision made by a person, so none of them happens automatically.
    </div>
  `,
})
export class StudentShellComponent {
  constructor(protected readonly authService: AuthService) {}
}
