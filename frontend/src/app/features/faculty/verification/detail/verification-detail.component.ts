import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { EvidenceService } from '../../../../core/services/evidence.service';
import { Evidence, EvidenceVersion, VerificationDecision } from '../../../../core/models/evidence.model';
import { SecureImageComponent } from '../../../../shared/secure-image/secure-image.component';

type DecisionAction = 'VERIFY' | 'REJECT' | 'RESUBMIT' | null;

@Component({
  selector: 'app-verification-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, SecureImageComponent],
  templateUrl: './verification-detail.component.html',
})
export class VerificationDetailComponent implements OnInit {
  readonly evidence = signal<Evidence | null>(null);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly pendingAction = signal<DecisionAction>(null);
  readonly submitting = signal(false);
  reason = '';

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

  canDecide(): boolean {
    const evidence = this.evidence();
    return !!evidence && (evidence.status === 'SUBMITTED' || evidence.status === 'UNDER_REVIEW');
  }

  startAction(action: DecisionAction): void {
    this.pendingAction.set(action);
    this.reason = '';
    this.errorMessage.set(null);
  }

  cancelAction(): void {
    this.pendingAction.set(null);
    this.reason = '';
  }

  confirmAction(): void {
    const action = this.pendingAction();
    if (!action) return;
    if (action !== 'VERIFY' && !this.reason.trim()) {
      this.errorMessage.set('A reason is required for this decision.');
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    const call$ = action === 'VERIFY'
      ? this.evidenceService.verify(this.evidenceId, this.reason.trim())
      : action === 'REJECT'
        ? this.evidenceService.reject(this.evidenceId, this.reason.trim())
        : this.evidenceService.requestResubmission(this.evidenceId, this.reason.trim());

    call$.subscribe({
      next: (evidence) => {
        this.evidence.set(evidence);
        this.submitting.set(false);
        this.pendingAction.set(null);
        this.reason = '';
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
