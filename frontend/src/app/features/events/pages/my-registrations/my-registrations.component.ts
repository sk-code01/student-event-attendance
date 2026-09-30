import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';
import { RegistrationService } from '../../../../core/services/registration.service';
import { Registration } from '../../../../core/models/registration.model';

@Component({
  selector: 'app-my-registrations',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './my-registrations.component.html',
})
export class MyRegistrationsComponent implements OnInit {
  readonly registrations = signal<Registration[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly cancellingId = signal<number | null>(null);

  constructor(private readonly registrationService: RegistrationService) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.registrationService.list().subscribe({
      next: (page) => {
        this.registrations.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load your registrations.');
        this.loading.set(false);
      },
    });
  }

  canCancel(registration: Registration): boolean {
    if (registration.status !== 'REGISTERED') return false;
    return new Date(registration.event.event_date) >= new Date(new Date().toDateString());
  }

  cancel(registration: Registration): void {
    this.cancellingId.set(registration.id);
    this.errorMessage.set(null);
    this.registrationService.cancel(registration.id).subscribe({
      next: (updated) => {
        this.cancellingId.set(null);
        this.registrations.update((list) => list.map((r) => (r.id === updated.id ? updated : r)));
      },
      error: (error: HttpErrorResponse) => {
        this.cancellingId.set(null);
        this.errorMessage.set(error.error?.detail ?? 'Unable to cancel this registration.');
      },
    });
  }
}
