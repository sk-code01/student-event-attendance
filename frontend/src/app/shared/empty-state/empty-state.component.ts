import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Role-aware empty state.
 *
 * An empty list is a moment where the interface should say what is going on
 * and, where there is one, offer the next step. "No data" tells a Faculty
 * member nothing; "You're all caught up" tells them their queue is clear.
 * The caller supplies the wording because only the caller knows the context.
 */
@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="empty-state">
      <div class="empty-state-icon" aria-hidden="true">
        <svg viewBox="0 0 20 20" fill="currentColor">
          @switch (icon()) {
            @case ('check') {
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.7-9.7a1 1 0 00-1.4-1.4L9 10.2 7.7 8.9a1 1 0 10-1.4 1.4l2 2a1 1 0 001.4 0l4-4z" clip-rule="evenodd" />
            }
            @case ('calendar') {
              <path fill-rule="evenodd" d="M6 2a1 1 0 011 1v1h6V3a1 1 0 112 0v1h1a2 2 0 012 2v9a2 2 0 01-2 2H4a2 2 0 01-2-2V6a2 2 0 012-2h1V3a1 1 0 011-1zM4 8v7h12V8H4z" clip-rule="evenodd" />
            }
            @case ('users') {
              <path d="M7 9a3 3 0 100-6 3 3 0 000 6zM3.5 17a3.5 3.5 0 017 0v1h-7v-1zM14 9a2.5 2.5 0 100-5 2.5 2.5 0 000 5zm-1.6 2.2A4.5 4.5 0 0117 15.5V18h-2.6v-1a5.4 5.4 0 00-2-4.2 4 4 0 011-.6z" />
            }
            @case ('camera') {
              <path fill-rule="evenodd" d="M7.4 3a1 1 0 00-.83.44L5.87 4.5H4a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1.87l-.7-1.06A1 1 0 0012.6 3H7.4zM10 7a3.5 3.5 0 110 7 3.5 3.5 0 010-7zm0 2a1.5 1.5 0 100 3 1.5 1.5 0 000-3z" clip-rule="evenodd" />
            }
            @case ('search') {
              <path fill-rule="evenodd" d="M9 3.5a5.5 5.5 0 103.4 9.8l3.4 3.4a1 1 0 001.4-1.4l-3.4-3.4A5.5 5.5 0 009 3.5zM5.5 9a3.5 3.5 0 117 0 3.5 3.5 0 01-7 0z" clip-rule="evenodd" />
            }
            @default {
              <path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm2 4h8a1 1 0 110 2H6a1 1 0 010-2zm0 4h5a1 1 0 110 2H6a1 1 0 010-2z" clip-rule="evenodd" />
            }
          }
        </svg>
      </div>

      <h2 class="empty-state-title">{{ title() }}</h2>
      @if (message()) {
        <p class="empty-state-text">{{ message() }}</p>
      }

      @if (actionLabel() && actionLink()) {
        <div class="empty-state-actions">
          <a [routerLink]="actionLink()" class="btn btn-primary btn-sm">{{ actionLabel() }}</a>
        </div>
      }
    </div>
  `,
})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly message = input<string | null>(null);
  readonly icon = input<'inbox' | 'check' | 'calendar' | 'users' | 'search' | 'camera'>('inbox');
  readonly actionLabel = input<string | null>(null);
  readonly actionLink = input<string | null>(null);
}
