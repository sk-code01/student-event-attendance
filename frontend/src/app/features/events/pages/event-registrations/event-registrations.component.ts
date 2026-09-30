import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { AuthService } from '../../../../core/services/auth.service';
import { EventService } from '../../../../core/services/event.service';
import { RegistrationService } from '../../../../core/services/registration.service';
import { Event } from '../../../../core/models/event.model';
import { Registration } from '../../../../core/models/registration.model';
import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-event-registrations',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-registrations.component.html',
})
export class EventRegistrationsComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly eventService = inject(EventService);
  private readonly registrationService = inject(RegistrationService);
  protected readonly authService = inject(AuthService);

  readonly event = signal<Event | null>(null);
  readonly registrations = signal<Registration[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  protected get basePath(): string {
    return this.authService.hasRole('ADMIN') ? '/admin' : '/event-coordinator';
  }

  ngOnInit(): void {
    const eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.eventService.get(eventId).subscribe({ next: (event) => this.event.set(event) });
    this.registrationService.list(eventId).subscribe({
      next: (page) => {
        this.registrations.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load registrations for this event.');
        this.loading.set(false);
      },
    });
  }
}
