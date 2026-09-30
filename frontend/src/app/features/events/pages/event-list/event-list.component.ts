import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

import { EventService } from '../../../../core/services/event.service';
import { Event } from '../../../../core/models/event.model';

@Component({
  selector: 'app-event-list',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-list.component.html',
})
export class EventListComponent implements OnInit {
  readonly events = signal<Event[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(private readonly eventService: EventService) {}

  ngOnInit(): void {
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
      default: return 'text-bg-secondary';
    }
  }
}
