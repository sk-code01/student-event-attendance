import { Component, ElementRef, HostListener, ViewChild, input, output } from '@angular/core';

export type ConfirmTone = 'danger' | 'warning' | 'neutral';

/**
 * Confirmation for a destructive or irreversible action.
 *
 * Deliberately more than "Are you sure?": it takes a `consequence` line,
 * because what the user needs to weigh is what will happen, not whether they
 * meant to click. A dialog that cannot explain its consequence usually did
 * not need to exist.
 *
 * Accessibility: `role="dialog"` + `aria-modal`, focus moved to the confirm
 * button on open, Escape cancels, and focus is trapped between the two
 * actions so Tab cannot wander behind the backdrop.
 */
@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  template: `
    <div class="dialog-backdrop" (click)="onBackdrop($event)">
      <div
        class="dialog"
        [class.is-danger]="tone() === 'danger'"
        [class.is-warning]="tone() === 'warning'"
        role="dialog"
        aria-modal="true"
        [attr.aria-labelledby]="titleId"
        [attr.aria-describedby]="bodyId"
        (click)="$event.stopPropagation()"
      >
        <div class="dialog-head">
          <div class="dialog-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="currentColor">
              @if (tone() === 'danger') {
                <path fill-rule="evenodd" d="M9 2a1 1 0 00-.9.6L7.4 4H4a1 1 0 000 2h12a1 1 0 100-2h-3.4l-.7-1.4A1 1 0 0011 2H9zM5 7h10l-.7 9.1A2 2 0 0112.3 18H7.7a2 2 0 01-2-1.9L5 7z" clip-rule="evenodd" />
              } @else {
                <path fill-rule="evenodd" d="M8.3 2.9c.8-1.3 2.6-1.3 3.4 0l6 10.2c.8 1.3-.2 3-1.7 3H4c-1.5 0-2.5-1.7-1.7-3l6-10.2zM10 7a1 1 0 00-1 1v3a1 1 0 102 0V8a1 1 0 00-1-1zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
              }
            </svg>
          </div>
          <div>
            <h2 class="dialog-title" [id]="titleId">{{ title() }}</h2>
            <p class="dialog-text" [id]="bodyId">{{ message() }}</p>
          </div>
        </div>

        @if (consequence()) {
          <p class="dialog-consequence">{{ consequence() }}</p>
        }

        <div class="dialog-actions">
          <button
            #cancelButton
            type="button"
            class="btn btn-outline-secondary"
            [disabled]="busy()"
            (click)="cancelled.emit()"
          >
            {{ cancelLabel() }}
          </button>
          <button
            #confirmButton
            type="button"
            class="btn"
            [class.btn-danger]="tone() === 'danger'"
            [class.btn-primary]="tone() !== 'danger'"
            [disabled]="busy()"
            (click)="confirmed.emit()"
          >
            @if (busy()) {
              <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
              {{ busyLabel() }}
            } @else {
              {{ confirmLabel() }}
            }
          </button>
        </div>
      </div>
    </div>
  `,
})
export class ConfirmDialogComponent {
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  /** What will actually happen. Shown in a highlighted block when present. */
  readonly consequence = input<string | null>(null);
  readonly confirmLabel = input('Confirm');
  readonly busyLabel = input('Working…');
  readonly cancelLabel = input('Cancel');
  readonly tone = input<ConfirmTone>('danger');
  readonly busy = input(false);
  /** A stray click on the backdrop should not confirm; it may cancel. */
  readonly dismissOnBackdrop = input(true);

  readonly confirmed = output<void>();
  readonly cancelled = output<void>();

  protected readonly titleId = `dlg-t-${Math.random().toString(36).slice(2, 9)}`;
  protected readonly bodyId = `dlg-b-${Math.random().toString(36).slice(2, 9)}`;

  @ViewChild('confirmButton') private confirmButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('cancelButton') private cancelButton?: ElementRef<HTMLButtonElement>;

  ngAfterViewInit(): void {
    // Focus the confirm action so a keyboard user lands inside the dialog
    // rather than behind it.
    this.confirmButton?.nativeElement.focus();
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (!this.busy()) {
      this.cancelled.emit();
    }
  }

  /** A minimal focus trap: two focusable elements, so wrap between them.
   *  The parameter is typed `Event` because that is what Angular's
   *  HostListener contract provides; it is narrowed on the first line. */
  @HostListener('document:keydown.tab', ['$event'])
  @HostListener('document:keydown.shift.tab', ['$event'])
  protected trapFocus(event: Event): void {
    if (!(event instanceof KeyboardEvent)) {
      return;
    }
    const cancel = this.cancelButton?.nativeElement;
    const confirm = this.confirmButton?.nativeElement;
    if (!cancel || !confirm) {
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && active === cancel) {
      event.preventDefault();
      confirm.focus();
    } else if (!event.shiftKey && active === confirm) {
      event.preventDefault();
      cancel.focus();
    } else if (active !== cancel && active !== confirm) {
      event.preventDefault();
      confirm.focus();
    }
  }

  protected onBackdrop(event: MouseEvent): void {
    event.stopPropagation();
    if (this.dismissOnBackdrop() && !this.busy()) {
      this.cancelled.emit();
    }
  }
}
