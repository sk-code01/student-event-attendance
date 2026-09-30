import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { Achievement } from '../../../core/models/achievement.model';
import { Evidence } from '../../../core/models/evidence.model';
import { AchievementService } from '../../../core/services/achievement.service';
import { EvidenceService } from '../../../core/services/evidence.service';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

/**
 * Faculty record achievements against verified participations. The record they
 * create goes to PENDING_APPROVAL for their Event Coordinator — there is no approve control
 * here, not even for a record the same Faculty member created.
 */
@Component({
  selector: 'app-faculty-achievements',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './faculty-achievements.component.html',
})
export class FacultyAchievementsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);

  readonly verifiedEvidence = signal<Evidence[]>([]);
  readonly achievements = signal<Achievement[]>([]);
  readonly loading = signal(true);
  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    participation: [null as number | null, [Validators.required]],
    title: ['', [Validators.required]],
    achievement_type: ['', [Validators.required]],
    achievement_date: ['', [Validators.required]],
    description: [''],
  });

  constructor(
    private readonly achievementService: AchievementService,
    private readonly evidenceService: EvidenceService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    forkJoin({ evidence: this.evidenceService.list(), achievements: this.achievementService.list() }).subscribe({
      next: ({ evidence, achievements }) => {
        this.verifiedEvidence.set(evidence.results.filter((e) => e.status === 'VERIFIED'));
        this.achievements.set(achievements.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load achievements.');
        this.loading.set(false);
      },
    });
  }

  create(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);

    const raw = this.form.getRawValue();
    this.achievementService
      .create({
        participation: raw.participation as number,
        title: raw.title,
        achievement_type: raw.achievement_type,
        achievement_date: raw.achievement_date,
        description: raw.description,
      })
      .subscribe({
        next: (achievement) => {
          this.submitting.set(false);
          this.successMessage.set(`"${achievement.title}" submitted for Event Coordinator approval.`);
          this.achievements.update((list) => [achievement, ...list]);
          this.form.reset({ participation: null, title: '', achievement_type: '', achievement_date: '', description: '' });
        },
        error: (error: HttpErrorResponse) => {
          this.submitting.set(false);
          this.errorMessage.set(this.firstError(error) ?? 'Unable to create the achievement.');
        },
      });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-warning';
  }

  private firstError(error: HttpErrorResponse): string | null {
    const body = error.error;
    if (!body || typeof body !== 'object') {
      return null;
    }
    const first = Object.values(body)[0];
    return Array.isArray(first) ? String(first[0]) : String(first);
  }
}
