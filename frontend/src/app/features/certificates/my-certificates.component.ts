import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CertificateService } from '../../core/services/certificate.service';
import { ToastService } from '../../core/services/toast.service';
import { TrackingService } from '../../core/services/tracking.service';
import { Certificate } from '../../core/models/certificate.model';
import { TrackingRow } from '../../core/models/tracking.model';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

/**
 * The student's certificates, one row per event they took part in.
 *
 * Built on the tracking endpoint rather than the certificate list, because the
 * question here is "which of my events need a certificate?" — an event with no
 * certificate yet has no certificate record to list. The server decides
 * eligibility; this page only reports what it says, which is why the reason a
 * window is shut is shown verbatim rather than being re-derived here.
 */
@Component({
  selector: 'app-my-certificates',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './my-certificates.component.html',
})
export class MyCertificatesComponent implements OnInit {
  readonly rows = signal<TrackingRow[]>([]);
  readonly certificates = signal<Certificate[]>([]);
  readonly loading = signal(true);
  readonly uploadingFor = signal<number | null>(null);
  readonly errorMessage = signal<string | null>(null);

  constructor(
    private readonly tracking: TrackingService,
    private readonly certificateService: CertificateService,
    private readonly toast: ToastService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    this.tracking.list().subscribe({
      next: (page) => {
        this.rows.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load your events.');
        this.loading.set(false);
      },
    });

    // The certificate records themselves carry the rejection reasons and the
    // decisions, which the tracking row deliberately summarises rather than
    // repeats.
    this.certificateService.list().subscribe({
      next: (page) => this.certificates.set(page.results),
      error: () => this.certificates.set([]),
    });
  }

  /** The latest attempt for an event, which is the one the student is acting on. */
  latestFor(row: TrackingRow): Certificate | null {
    const mine = this.certificates()
      .filter((certificate) => certificate.participation === row.participation_id)
      .sort((a, b) => a.attempt_number - b.attempt_number);
    return mine.length ? mine[mine.length - 1] : null;
  }

  canUpload(row: TrackingRow): boolean {
    // Mirrors the server's rule so the button is not offered when it would be
    // refused; the server remains the authority either way.
    return (
      row.participation_id !== null
      && (row.certificate_status === 'NOT_SUBMITTED' || row.certificate_status === 'REJECTED')
      && row.certificate_attempts_remaining > 0
    );
  }

  statusLabel(row: TrackingRow): string {
    switch (row.certificate_status) {
      case 'NOT_ELIGIBLE': return 'Not eligible — no live capture';
      case 'WINDOW_NOT_OPEN': return 'Opens the day after the event';
      case 'NOT_SUBMITTED': return 'Not submitted';
      case 'SUBMITTED': return 'Awaiting Faculty verification';
      case 'VERIFIED': return 'Verified';
      case 'REJECTED': return 'Rejected';
      case 'ACCEPTED_BY_COORDINATOR': return 'Accepted by your Event Coordinator';
      default: return row.certificate_status;
    }
  }

  statusClass(row: TrackingRow): string {
    switch (row.certificate_status) {
      case 'VERIFIED':
      case 'ACCEPTED_BY_COORDINATOR': return 'text-bg-success';
      case 'REJECTED': return 'text-bg-danger';
      case 'SUBMITTED': return 'text-bg-info';
      default: return 'text-bg-secondary';
    }
  }

  onFileSelected(row: TrackingRow, event: globalThis.Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    // Clearing the input means picking the same file again still fires a
    // change event, which matters after a failed upload.
    input.value = '';
    if (!file || row.participation_id === null) {
      return;
    }

    this.uploadingFor.set(row.registration_id);
    this.certificateService.upload(row.participation_id, file).subscribe({
      next: () => {
        this.uploadingFor.set(null);
        this.toast.success('Certificate submitted. Your Faculty will verify it.');
        this.load();
      },
      error: (error: { error?: { detail?: string } | string[] }) => {
        this.uploadingFor.set(null);
        const body = error.error;
        const detail = Array.isArray(body) ? body[0] : body?.detail;
        this.toast.error(detail || 'Unable to submit the certificate.');
      },
    });
  }
}
