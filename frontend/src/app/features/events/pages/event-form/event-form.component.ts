import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidatorFn, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../../core/services/auth.service';
import { CollegeService } from '../../../../core/services/college.service';
import { EventService } from '../../../../core/services/event.service';
import { College } from '../../../../core/models/college.model';

function dateOnOrBefore(startKey: string, endKey: string): ValidatorFn {
  return (group: AbstractControl) => {
    const start = group.get(startKey)?.value;
    const end = group.get(endKey)?.value;
    if (!start || !end) return null;
    return start <= end ? null : { dateOrder: true };
  };
}

function dateStrictlyBefore(beforeKey: string, afterKey: string, errorKey: string): ValidatorFn {
  return (group: AbstractControl) => {
    const before = group.get(beforeKey)?.value;
    const after = group.get(afterKey)?.value;
    if (!before || !after) return null;
    return before < after ? null : { [errorKey]: true };
  };
}

@Component({
  selector: 'app-event-form',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './event-form.component.html',
})
export class EventFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);

  readonly colleges = signal<College[]>([]);
  readonly loading = signal(false);
  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly fieldErrors = signal<Record<string, string>>({});
  readonly isEditMode = signal(false);

  private eventId: number | null = null;

  readonly form = this.fb.nonNullable.group(
    {
      title: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(200)]],
      description: [''],
      event_date: ['', [Validators.required]],
      venue: ['', [Validators.required, Validators.minLength(2)]],
      category: ['', [Validators.required, Validators.minLength(2)]],
      conducting_college: [null as number | null, [Validators.required]],
      registration_start_date: ['', [Validators.required]],
      registration_end_date: ['', [Validators.required]],
    },
    {
      validators: [
        dateOnOrBefore('registration_start_date', 'registration_end_date'),
        dateStrictlyBefore('registration_end_date', 'event_date', 'registrationEndNotBeforeEventDate'),
      ],
    },
  );

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly eventService: EventService,
    private readonly collegeService: CollegeService,
    protected readonly authService: AuthService,
  ) {}

  protected get basePath(): string {
    return this.authService.hasRole('ADMIN') ? '/admin' : '/event-coordinator';
  }

  ngOnInit(): void {
    // `conducting_college` is a required field, so an empty dropdown is not a
    // cosmetic problem: the form becomes unsubmittable. Say so rather than
    // leaving the user to guess why the select has no options.
    this.collegeService.list({ all: true }).subscribe({
      next: (page) => this.colleges.set(page.results),
      error: () =>
        this.errorMessage.set('Unable to load the list of colleges. Reload the page before creating an event.'),
    });

    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.isEditMode.set(true);
      this.eventId = Number(idParam);
      this.loading.set(true);
      this.eventService.get(this.eventId).subscribe({
        next: (event) => {
          this.form.patchValue({
            title: event.title,
            description: event.description,
            event_date: event.event_date,
            venue: event.venue,
            category: event.category,
            conducting_college: event.conducting_college.id,
            registration_start_date: event.registration_start_date,
            registration_end_date: event.registration_end_date,
          });
          this.loading.set(false);
        },
        error: () => {
          this.errorMessage.set('Unable to load this event.');
          this.loading.set(false);
        },
      });
    }
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.fieldErrors.set({});

    const raw = this.form.getRawValue();
    const payload = { ...raw, conducting_college: raw.conducting_college as number };

    const request$ = this.isEditMode() && this.eventId
      ? this.eventService.update(this.eventId, payload)
      : this.eventService.create(payload);

    request$.subscribe({
      next: () => {
        this.submitting.set(false);
        this.router.navigateByUrl(`${this.basePath}/events`);
      },
      error: (error: HttpErrorResponse) => {
        this.submitting.set(false);
        this.handleError(error);
      },
    });
  }

  private handleError(error: HttpErrorResponse): void {
    const body = error.error;
    if (body && typeof body === 'object') {
      const fieldErrors: Record<string, string> = {};
      for (const [key, value] of Object.entries(body)) {
        fieldErrors[key] = Array.isArray(value) ? value[0] : String(value);
      }
      this.fieldErrors.set(fieldErrors);
    }
    if (!body || Object.keys(body).length === 0) {
      this.errorMessage.set('Unable to save this event. Please review the form and try again.');
    }
  }
}
