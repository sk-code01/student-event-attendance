import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-unauthorized',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="d-flex flex-column align-items-center justify-content-center text-center" style="min-height: 100vh;">
      <div class="display-6 mb-3">🚫</div>
      <h1 class="h4 mb-2">Not authorized</h1>
      <p class="text-muted small mb-4">You don't have permission to view this page.</p>
      <a routerLink="/login" class="btn btn-outline-primary">Back to sign in</a>
    </div>
  `,
})
export class UnauthorizedComponent {}
