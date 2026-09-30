import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { RegistrationRequestService } from '../../core/services/registration-request.service';
import { RegistrationRequest } from '../../core/models/registration-request.model';

@Component({
  selector: 'app-event-coordinator-shell',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink],
  templateUrl: './event-coordinator-shell.component.html',
})
export class EventCoordinatorShellComponent implements OnInit {
  readonly requests = signal<RegistrationRequest[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly actioningId = signal<number | null>(null);
  readonly rejectingId = signal<number | null>(null);
  rejectionReason = '';

  constructor(
    protected readonly authService: AuthService,
    private readonly registrationRequestService: RegistrationRequestService,
  ) {}

  ngOnInit(): void {
    this.loadPending();
  }

  loadPending(): void {
    this.loading.set(true);
    this.registrationRequestService.list('PENDING').subscribe({
      next: (page) => {
        this.requests.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load registration requests.');
        this.loading.set(false);
      },
    });
  }

  approve(request: RegistrationRequest): void {
    this.actioningId.set(request.id);
    this.registrationRequestService.approve(request.id).subscribe({
      next: () => {
        this.actioningId.set(null);
        this.requests.update((list) => list.filter((r) => r.id !== request.id));
      },
      error: (error: HttpErrorResponse) => {
        this.actioningId.set(null);
        this.errorMessage.set(error.error?.detail ?? 'Unable to approve this request.');
      },
    });
  }

  startReject(request: RegistrationRequest): void {
    this.rejectingId.set(request.id);
    this.rejectionReason = '';
  }

  cancelReject(): void {
    this.rejectingId.set(null);
    this.rejectionReason = '';
  }

  confirmReject(request: RegistrationRequest): void {
    if (!this.rejectionReason.trim()) {
      return;
    }
    this.actioningId.set(request.id);
    this.registrationRequestService.reject(request.id, this.rejectionReason.trim()).subscribe({
      next: () => {
        this.actioningId.set(null);
        this.rejectingId.set(null);
        this.requests.update((list) => list.filter((r) => r.id !== request.id));
      },
      error: (error: HttpErrorResponse) => {
        this.actioningId.set(null);
        this.errorMessage.set(error.error?.detail ?? 'Unable to reject this request.');
      },
    });
  }
}
