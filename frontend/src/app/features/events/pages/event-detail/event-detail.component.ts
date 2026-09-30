import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { EventService } from '../../../../core/services/event.service';
import { ParticipationService } from '../../../../core/services/participation.service';
import { RegistrationService } from '../../../../core/services/registration.service';
import { Event } from '../../../../core/models/event.model';
import { EligibilityResult } from '../../../../core/models/participation.model';

@Component({
  selector: 'app-event-detail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './event-detail.component.html',
})
export class EventDetailComponent implements OnInit {
  readonly event = signal<Event | null>(null);
  readonly loading = signal(true);
  readonly actionInProgress = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly participationEligibility = signal<EligibilityResult | null>(null);

  private eventId!: number;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly eventService: EventService,
    private readonly registrationService: RegistrationService,
    private readonly participationService: ParticipationService,
  ) {}

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.eventService.get(this.eventId).subscribe({
      next: (event) => {
        this.event.set(event);
        this.loading.set(false);
        if (event.my_registration_status === 'REGISTERED') {
          this.loadParticipationEligibility();
        }
      },
      error: () => {
        this.errorMessage.set('Unable to load this event.');
        this.loading.set(false);
      },
    });
  }

  private loadParticipationEligibility(): void {
    this.participationService.checkEligibility(this.eventId).subscribe({
      next: (result) => this.participationEligibility.set(result),
      // A failed eligibility check is non-fatal to viewing the event page —
      // the "Mark Participation" section simply won't render.
      error: () => this.participationEligibility.set(null),
    });
  }

  register(): void {
    this.actionInProgress.set(true);
    this.errorMessage.set(null);
    this.registrationService.register(this.eventId).subscribe({
      next: () => {
        this.actionInProgress.set(false);
        this.successMessage.set('You have been registered for this event.');
        this.load();
      },
      error: (error: HttpErrorResponse) => {
        this.actionInProgress.set(false);
        this.errorMessage.set(this.firstError(error) ?? 'Unable to register for this event.');
      },
    });
  }

  private firstError(error: HttpErrorResponse): string | null {
    const body = error.error;
    if (!body || typeof body !== 'object') return null;
    const firstKey = Object.keys(body)[0];
    if (!firstKey) return null;
    const value = body[firstKey];
    return Array.isArray(value) ? value[0] : String(value);
  }
}
