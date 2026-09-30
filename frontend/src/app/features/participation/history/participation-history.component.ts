import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { OfflineCaptureQueueService, QueuedSession } from '../../../core/services/offline-capture-queue.service';
import { ParticipationService } from '../../../core/services/participation.service';
import { Participation } from '../../../core/models/participation.model';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-participation-history',
  standalone: true,
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './participation-history.component.html',
})
export class ParticipationHistoryComponent implements OnInit {
  readonly participations = signal<Participation[]>([]);
  readonly queuedSessions = signal<QueuedSession[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(
    private readonly participationService: ParticipationService,
    private readonly offlineQueue: OfflineCaptureQueueService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.participationService.list().subscribe({
      next: (page) => {
        this.participations.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load your participation history.');
        this.loading.set(false);
      },
    });
    this.offlineQueue.listForCurrentUser().then((sessions) => this.queuedSessions.set(sessions));
  }

  retrySync(): void {
    this.offlineQueue.syncAll().then(() => this.load());
  }

  discardQueued(id: string): void {
    this.offlineQueue.discard(id).then(() => this.load());
  }
}
