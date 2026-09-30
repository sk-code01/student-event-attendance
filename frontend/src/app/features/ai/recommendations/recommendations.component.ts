import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { RecommendationsResponse } from '../../../core/models/ai.model';
import { AiService } from '../../../core/services/ai.service';
import { AiDisclaimerComponent } from '../../../shared/ai-disclaimer/ai-disclaimer.component';
import { httpErrorMessage, reasonMessage } from '../ai-state';

/**
 * Student event recommendations.
 *
 * Renders the backend's ranked list and its feature-backed reasons verbatim.
 * The score is shown as the backend describes it (a similarity, not a
 * probability) and the cold-start case is labelled as such rather than
 * dressed up as a model output. The only action offered is the ordinary
 * event page — registering remains the student's own choice.
 */
@Component({
  selector: 'app-recommendations',
  standalone: true,
  imports: [DatePipe, DecimalPipe, RouterLink, AiDisclaimerComponent],
  templateUrl: './recommendations.component.html',
})
export class RecommendationsComponent implements OnInit {
  private readonly aiService = inject(AiService);

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly response = signal<RecommendationsResponse | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.aiService.recommendations().subscribe({
      next: (response) => {
        this.response.set(response);
        this.loading.set(false);
      },
      error: (error) => {
        this.errorMessage.set(httpErrorMessage(error));
        this.loading.set(false);
      },
    });
  }

  unavailableMessage(response: RecommendationsResponse): string {
    return reasonMessage(response.reason, response.detail);
  }
}
