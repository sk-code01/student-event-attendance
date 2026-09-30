import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { AttendanceService } from '../../../core/services/attendance.service';
import { EventService } from '../../../core/services/event.service';
import { ToastService } from '../../../core/services/toast.service';
import { TrackingService } from '../../../core/services/tracking.service';
import { Event as CollegeEvent } from '../../../core/models/event.model';
import { TrackingFilters, TrackingRow } from '../../../core/models/tracking.model';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

/**
 * Department-wide tracking: every registered student against every stage of
 * the workflow, with the filters a coordinator actually needs.
 *
 * The statuses shown are computed by the server, never stored. In particular
 * "Not submitted" says the event date passed without a live capture — it is a
 * prompt for the coordinator to decide attendance, never a decision in itself,
 * which is why marking attendance here is an explicit action with a confirm.
 */
@Component({
  selector: 'app-event-coordinator-tracking',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-coordinator-tracking.component.html',
})
export class EventCoordinatorTrackingComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);

  readonly rows = signal<TrackingRow[]>([]);
  readonly events = signal<CollegeEvent[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly markingId = signal<number | null>(null);

  /** Bound to the filter bar. Empty values are dropped before the request. */
  filters: TrackingFilters = {
    event: null,
    search: '',
    live_capture_status: '',
    verification_status: '',
    certificate_status: '',
    attendance_status: '',
  };

  readonly liveCaptureOptions = [
    { value: '', label: 'Any live capture status' },
    { value: 'SUBMITTED', label: 'Submitted' },
    { value: 'NOT_SUBMITTED', label: 'Not submitted' },
    { value: 'IN_PROGRESS', label: 'In progress' },
    { value: 'OPEN_TODAY', label: 'Open today' },
    { value: 'AWAITING_EVENT', label: 'Awaiting event' },
  ];

  readonly certificateOptions = [
    { value: '', label: 'Any certificate status' },
    { value: 'NOT_ELIGIBLE', label: 'Not eligible' },
    { value: 'WINDOW_NOT_OPEN', label: 'Window not open' },
    { value: 'NOT_SUBMITTED', label: 'Not submitted' },
    { value: 'SUBMITTED', label: 'Awaiting verification' },
    { value: 'VERIFIED', label: 'Verified' },
    { value: 'REJECTED', label: 'Rejected' },
    { value: 'ACCEPTED_BY_COORDINATOR', label: 'Accepted by coordinator' },
  ];

  readonly attendanceOptions = [
    { value: '', label: 'Any attendance status' },
    { value: 'NOT_RECORDED', label: 'Not recorded' },
    { value: 'PENDING', label: 'Pending' },
    { value: 'APPROVED', label: 'Approved' },
    { value: 'REJECTED', label: 'Rejected' },
  ];

  constructor(
    private readonly tracking: TrackingService,
    private readonly attendance: AttendanceService,
    private readonly eventService: EventService,
    private readonly toast: ToastService,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.eventService.list().subscribe({
      next: (page) => this.events.set(page.results),
      // The event filter is a convenience; losing it must not stop the page
      // from showing the rows themselves.
      error: () => this.events.set([]),
    });

    // Deep links from the dashboard and from a student's row arrive as query
    // parameters, so the page opens already narrowed.
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const event = params.get('event');
      const student = params.get('student');
      this.filters = {
        ...this.filters,
        event: event ? Number(event) : null,
        student: student ? Number(student) : null,
      };
      this.load();
    });
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.tracking.list(this.filters).subscribe({
      next: (page) => {
        this.rows.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load the tracking view.');
        this.loading.set(false);
      },
    });
  }

  clearFilters(): void {
    this.filters = {
      event: null,
      student: null,
      search: '',
      live_capture_status: '',
      verification_status: '',
      certificate_status: '',
      attendance_status: '',
    };
    this.load();
  }

  /**
   * Records attendance for one row. Rejection requires a reason, which the
   * backend also enforces — asking here simply saves a failed round trip.
   */
  markAttendance(row: TrackingRow, status: 'APPROVED' | 'REJECTED'): void {
    let reason = '';
    if (status === 'REJECTED') {
      reason = (window.prompt('Reason for rejecting attendance:') ?? '').trim();
      if (!reason) {
        return;
      }
    }

    this.markingId.set(row.registration_id);
    this.attendance.mark(row.registration_id, status, reason).subscribe({
      next: () => {
        this.markingId.set(null);
        this.toast.success(
          `Attendance ${status === 'APPROVED' ? 'approved' : 'rejected'} for ${this.displayName(row)}.`,
        );
        this.load();
      },
      error: () => {
        this.markingId.set(null);
        this.toast.error('Unable to record attendance.');
      },
    });
  }

  displayName(row: TrackingRow): string {
    return row.student.full_name || row.student.username;
  }

  liveCaptureLabel(row: TrackingRow): string {
    switch (row.live_capture_status) {
      case 'SUBMITTED': return 'Submitted';
      case 'NOT_SUBMITTED': return 'Not submitted';
      case 'IN_PROGRESS': return 'In progress';
      case 'OPEN_TODAY': return 'Open today';
      default: return 'Awaiting event';
    }
  }

  liveCaptureClass(row: TrackingRow): string {
    switch (row.live_capture_status) {
      case 'SUBMITTED': return 'text-bg-success';
      case 'NOT_SUBMITTED': return 'text-bg-warning';
      case 'IN_PROGRESS': return 'text-bg-info';
      default: return 'text-bg-secondary';
    }
  }

  certificateClass(row: TrackingRow): string {
    switch (row.certificate_status) {
      case 'VERIFIED':
      case 'ACCEPTED_BY_COORDINATOR': return 'text-bg-success';
      case 'REJECTED': return 'text-bg-danger';
      case 'SUBMITTED': return 'text-bg-info';
      default: return 'text-bg-secondary';
    }
  }

  attendanceClass(row: TrackingRow): string {
    switch (row.attendance_status) {
      case 'APPROVED': return 'text-bg-success';
      case 'REJECTED': return 'text-bg-danger';
      case 'PENDING': return 'text-bg-warning';
      default: return 'text-bg-secondary';
    }
  }
}
