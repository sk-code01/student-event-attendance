import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { EvidenceService } from '../../../core/services/evidence.service';
import { Evidence, EvidenceVersion } from '../../../core/models/evidence.model';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-event-coordinator-verification-list',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-coordinator-verification-list.component.html',
})
export class EventCoordinatorVerificationListComponent implements OnInit {
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
        this.errorMessage.set('Unable to load evidence for your department.');
        this.loading.set(false);
      },
    });
  }

  latestVersion(evidence: Evidence): EvidenceVersion | null {
    return evidence.versions[evidence.versions.length - 1] ?? null;
  }
}
