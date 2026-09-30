import { CommonModule } from '@angular/common';
import { Observable } from 'rxjs';
import { Component, OnInit, computed, inject, signal } from '@angular/core';

import { AuthService } from '../../core/services/auth.service';
import { CertificateService } from '../../core/services/certificate.service';
import { ToastService } from '../../core/services/toast.service';
import { Certificate } from '../../core/models/certificate.model';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

/**
 * Certificate review, for the two roles that decide on one.
 *
 * Faculty verify or reject a submission; the Event Coordinator then records
 * the final decision on what Faculty verified, and separately may accept a
 * rejected certificate once the student's three attempts are gone. Those are
 * genuinely different powers over the same record, so this page offers each
 * role only its own — while the backend enforces the same boundary regardless
 * of what this page renders.
 */
@Component({
  selector: 'app-certificate-review',
  standalone: true,
  imports: [CommonModule, EmptyStateComponent],
  templateUrl: './certificate-review.component.html',
})
export class CertificateReviewComponent implements OnInit {
  private readonly auth = inject(AuthService);

  readonly certificates = signal<Certificate[]>([]);
  readonly loading = signal(true);
  readonly busyId = signal<number | null>(null);
  readonly errorMessage = signal<string | null>(null);

  readonly isFaculty = computed(() => this.auth.currentUser()?.role === 'FACULTY');
  readonly isCoordinator = computed(() => this.auth.currentUser()?.role === 'EVENT_COORDINATOR');

  constructor(
    private readonly certificateService: CertificateService,
    private readonly toast: ToastService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.certificateService.list().subscribe({
      next: (page) => {
        this.certificates.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load certificates.');
        this.loading.set(false);
      },
    });
  }

  /** Faculty act on submissions that nobody has decided yet. */
  awaitingVerification(certificate: Certificate): boolean {
    return this.isFaculty() && certificate.status === 'SUBMITTED';
  }

  /** The coordinator's decision comes after verification, never instead of it. */
  awaitingFinalDecision(certificate: Certificate): boolean {
    return this.isCoordinator() && certificate.awaits_final_decision;
  }

  /** The release valve for a student who has run out of attempts. */
  canAcceptExhausted(certificate: Certificate): boolean {
    return (
      this.isCoordinator()
      && certificate.status === 'REJECTED'
      && certificate.attempts_remaining === 0
    );
  }

  verify(certificate: Certificate): void {
    this.run(certificate, this.certificateService.decide(certificate.id, 'VERIFIED'), 'Certificate verified.');
  }

  reject(certificate: Certificate): void {
    const reason = (window.prompt('Reason for rejecting this certificate:') ?? '').trim();
    if (!reason) {
      // A bare rejection is not actionable for the student, and the backend
      // refuses it too.
      return;
    }
    this.run(
      certificate,
      this.certificateService.decide(certificate.id, 'REJECTED', reason),
      'Certificate rejected.',
    );
  }

  finalAccept(certificate: Certificate): void {
    this.run(
      certificate,
      this.certificateService.finalDecision(certificate.id, 'ACCEPTED'),
      'Final decision recorded: accepted.',
    );
  }

  finalReject(certificate: Certificate): void {
    const reason = (window.prompt('Reason for the final rejection:') ?? '').trim();
    if (!reason) {
      return;
    }
    this.run(
      certificate,
      this.certificateService.finalDecision(certificate.id, 'REJECTED', reason),
      'Final decision recorded: rejected.',
    );
  }

  acceptExhausted(certificate: Certificate): void {
    this.run(
      certificate,
      this.certificateService.acceptExhausted(certificate.id),
      'Rejected certificate accepted.',
    );
  }

  /** One place for the shared shape of every decision: mark busy, report the
   *  outcome, reload. The server's own message is preferred on failure,
   *  because it states the rule that was actually broken. */
  private run(certificate: Certificate, request: Observable<Certificate>, successMessage: string): void {
    this.busyId.set(certificate.id);
    request.subscribe({
      next: () => {
        this.busyId.set(null);
        this.toast.success(successMessage);
        this.load();
      },
      error: (error: { error?: { detail?: string } | string[] }) => {
        this.busyId.set(null);
        const body = error.error;
        const detail = Array.isArray(body) ? body[0] : body?.detail;
        this.toast.error(detail || 'The action could not be completed.');
      },
    });
  }

  statusClass(certificate: Certificate): string {
    switch (certificate.status) {
      case 'VERIFIED':
      case 'ACCEPTED_BY_COORDINATOR': return 'text-bg-success';
      case 'REJECTED': return 'text-bg-danger';
      default: return 'text-bg-info';
    }
  }

  studentName(certificate: Certificate): string {
    return certificate.student.username;
  }
}
