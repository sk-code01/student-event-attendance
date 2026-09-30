import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { EvidenceService } from '../../../core/services/evidence.service';
import { Evidence, EvidenceVersion, VerificationDecision } from '../../../core/models/evidence.model';
import { SecureImageComponent } from '../../../shared/secure-image/secure-image.component';

@Component({
  selector: 'app-event-coordinator-verification-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, SecureImageComponent],
  templateUrl: './event-coordinator-verification-detail.component.html',
})
export class EventCoordinatorVerificationDetailComponent implements OnInit {
  readonly evidence = signal<Evidence | null>(null);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly overriding = signal(false);
  readonly submitting = signal(false);
  overrideDecision: VerificationDecision = 'VERIFIED';
  overrideReason = '';

  private evidenceId!: number;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly evidenceService: EvidenceService,
  ) {}

  ngOnInit(): void {
    this.evidenceId = Number(this.route.snapshot.paramMap.get('id'));
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.evidenceService.get(this.evidenceId).subscribe({
      next: (evidence) => {
        this.evidence.set(evidence);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load this evidence record.');
        this.loading.set(false);
      },
    });
  }

  latestVersion(): EvidenceVersion | null {
    const evidence = this.evidence();
    return evidence ? evidence.versions[evidence.versions.length - 1] : null;
  }

  facultyDecision() {
    return this.latestVersion()?.verifications.find((v) => !v.is_event_coordinator_override) ?? null;
  }

  hodOverrides() {
    return this.latestVersion()?.verifications.filter((v) => v.is_event_coordinator_override) ?? [];
  }

  canOverride(): boolean {
    return !!this.facultyDecision();
  }

  startOverride(): void {
    this.overriding.set(true);
    this.overrideDecision = 'VERIFIED';
    this.overrideReason = '';
    this.errorMessage.set(null);
  }

  cancelOverride(): void {
    this.overriding.set(false);
    this.overrideReason = '';
  }

  confirmOverride(): void {
    if (!this.overrideReason.trim()) {
      this.errorMessage.set('A reason is required for an Event Coordinator override.');
      return;
    }
    this.submitting.set(true);
    this.errorMessage.set(null);
    this.evidenceService.override(this.evidenceId, this.overrideDecision, this.overrideReason.trim()).subscribe({
      next: (evidence) => {
        this.evidence.set(evidence);
        this.submitting.set(false);
        this.overriding.set(false);
        this.overrideReason = '';
      },
      error: (error: HttpErrorResponse) => {
        this.submitting.set(false);
        this.errorMessage.set(this.describeError(error));
      },
    });
  }

  private describeError(error: HttpErrorResponse): string {
    const body = error.error as Record<string, unknown> | undefined;
    if (body && typeof body === 'object') {
      const firstKey = Object.keys(body)[0];
      const value = firstKey ? body[firstKey] : null;
      if (value) return Array.isArray(value) ? String(value[0]) : String(value);
    }
    return 'This action could not be completed.';
  }

  decisionLabel(decision: VerificationDecision): string {
    return decision.replace('_', ' ');
  }
}
