import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';
import { EvidenceService } from '../../../../core/services/evidence.service';
import { Evidence, EvidenceVersion } from '../../../../core/models/evidence.model';

@Component({
  selector: 'app-verification-queue',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './verification-queue.component.html',
})
export class VerificationQueueComponent implements OnInit {
  readonly evidenceList = signal<Evidence[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(private readonly evidenceService: EvidenceService) {}

  ngOnInit(): void {
    this.loading.set(true);
    this.evidenceService.list().subscribe({
      next: (page) => {
        this.evidenceList.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load the verification queue.');
        this.loading.set(false);
      },
    });
  }

  latestVersion(evidence: Evidence): EvidenceVersion | null {
    return evidence.versions[evidence.versions.length - 1] ?? null;
  }

  hasLocationWarning(evidence: Evidence): boolean {
    return this.latestVersion(evidence)?.captures.some((c) => c.location_warning) ?? false;
  }
}
