import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';
import { CollegeService } from '../../../core/services/college.service';
import { College } from '../../../core/models/college.model';

@Component({
  selector: 'app-college-management',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './college-management.component.html',
})
export class CollegeManagementComponent implements OnInit {
  private readonly fb = inject(FormBuilder);

  readonly colleges = signal<College[]>([]);
  readonly loading = signal(true);
  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    code: ['', [Validators.required]],
  });

  constructor(private readonly collegeService: CollegeService) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.collegeService.list({ all: true }).subscribe({
      next: (page) => {
        this.colleges.set(page.results);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  create(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.errorMessage.set(null);
    this.collegeService.create(this.form.getRawValue()).subscribe({
      next: (college) => {
        this.submitting.set(false);
        this.colleges.update((list) => [...list, college]);
        this.form.reset();
      },
      error: (error: HttpErrorResponse) => {
        this.submitting.set(false);
        const body = error.error;
        const firstKey = body && typeof body === 'object' ? Object.keys(body)[0] : null;
        this.errorMessage.set(
          firstKey ? (Array.isArray(body[firstKey]) ? body[firstKey][0] : String(body[firstKey])) : 'Unable to create college.',
        );
      },
    });
  }
}
