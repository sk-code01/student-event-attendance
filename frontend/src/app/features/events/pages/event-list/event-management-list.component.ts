import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../../../core/services/auth.service';
import { EventService } from '../../../../core/services/event.service';
import { Event } from '../../../../core/models/event.model';
import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-event-management-list',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-management-list.component.html',
})
export class EventManagementListComponent implements OnInit {
  readonly events = signal<Event[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly actioningId = signal<number | null>(null);

  constructor(
    private readonly eventService: EventService,
    protected readonly authService: AuthService,
  ) {}

  /** '/event-coordinator' or '/admin' — this list is shared between both management areas. */
  protected get basePath(): string {
    return this.authService.hasRole('ADMIN') ? '/admin' : '/event-coordinator';
  }

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.eventService.list().subscribe({
      next: (page) => {
        this.events.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load events.');
        this.loading.set(false);
      },
    });
  }

  statusBadgeClass(status: Event['status']): string {
    switch (status) {
      case 'PUBLISHED': return 'text-bg-success';
      case 'CANCELLED': return 'text-bg-danger';
      case 'COMPLETED': return 'text-bg-secondary';
      default: return 'text-bg-warning';
    }
  }

  publish(event: Event): void {
    this.actioningId.set(event.id);
    this.errorMessage.set(null);
    this.eventService.publish(event.id).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (error: HttpErrorResponse) => this.handleActionError(error),
    });
  }

  cancel(event: Event): void {
    this.actioningId.set(event.id);
    this.errorMessage.set(null);
    this.eventService.cancel(event.id).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (error: HttpErrorResponse) => this.handleActionError(error),
    });
  }

  private applyUpdate(updated: Event): void {
    this.actioningId.set(null);
    this.events.update((list) => list.map((e) => (e.id === updated.id ? updated : e)));
  }

  private handleActionError(error: HttpErrorResponse): void {
    this.actioningId.set(null);
    this.errorMessage.set(error.error?.detail ?? 'Action failed.');
  }
}
