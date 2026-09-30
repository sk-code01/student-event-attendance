import { Component, inject } from '@angular/core';

import { ToastService } from '../../core/services/toast.service';

/**
 * Renders the toast stack. Mounted once, in the app root.
 *
 * `aria-live="polite"` on the region means a screen reader announces each
 * toast as it arrives without interrupting whatever the user is doing —
 * which is the right urgency for feedback on a completed action.
 */
@Component({
  selector: 'app-toast-container',
  standalone: true,
  template: `
    <div class="toast-stack" role="region" aria-live="polite" aria-label="Notifications">
      @for (toast of toastService.toasts(); track toast.id) {
        <div class="toast-item" [class]="'is-' + toast.kind">
          <svg class="toast-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            @switch (toast.kind) {
              @case ('success') {
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.7-9.7a1 1 0 00-1.4-1.4L9 10.2 7.7 8.9a1 1 0 10-1.4 1.4l2 2a1 1 0 001.4 0l4-4z" clip-rule="evenodd" />
              }
              @case ('error') {
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.7 7.3a1 1 0 00-1.4 1.4L8.6 10l-1.3 1.3a1 1 0 101.4 1.4L10 11.4l1.3 1.3a1 1 0 001.4-1.4L11.4 10l1.3-1.3a1 1 0 00-1.4-1.4L10 8.6 8.7 7.3z" clip-rule="evenodd" />
              }
              @case ('warning') {
                <path fill-rule="evenodd" d="M8.3 2.9c.8-1.3 2.6-1.3 3.4 0l6 10.2c.8 1.3-.2 3-1.7 3H4c-1.5 0-2.5-1.7-1.7-3l6-10.2zM10 7a1 1 0 00-1 1v3a1 1 0 102 0V8a1 1 0 00-1-1zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
              }
              @default {
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 11-2 0 1 1 0 012 0zm-1 3a1 1 0 00-1 1v3a1 1 0 102 0v-3a1 1 0 00-1-1z" clip-rule="evenodd" />
              }
            }
          </svg>

          <div class="toast-body">
            <div class="toast-title">{{ toast.title }}</div>
            @if (toast.text) {
              <div class="toast-text">{{ toast.text }}</div>
            }
          </div>

          <button
            type="button"
            class="btn-close btn-sm"
            [attr.aria-label]="'Dismiss: ' + toast.title"
            (click)="toastService.dismiss(toast.id)"
          ></button>
        </div>
      }
    </div>
  `,
})
export class ToastContainerComponent {
  protected readonly toastService = inject(ToastService);
}
