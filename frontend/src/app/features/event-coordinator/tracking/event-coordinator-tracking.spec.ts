import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AttendanceService } from '../../../core/services/attendance.service';
import { EventService } from '../../../core/services/event.service';
import { TrackingService } from '../../../core/services/tracking.service';
import { Attendance } from '../../../core/models/attendance.model';
import { TrackingRow } from '../../../core/models/tracking.model';
import { EventCoordinatorTrackingComponent } from './event-coordinator-tracking.component';

function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results };
}

const MARKED: Attendance = {
  id: 1,
  participation: null,
  registration: 7,
  student: { id: 1, username: 'stu1', role: 'STUDENT', department: 'MCA' },
  event: { id: 3, title: 'Tech Fest', event_date: '2026-09-01', venue: 'Hall' },
  status: 'APPROVED',
  is_manual: true,
  requested_by: null,
  requested_at: '',
  reviewed_by: { id: 2, username: 'ec1', role: 'EVENT_COORDINATOR' },
  reviewed_at: '',
  rejection_reason: '',
  created_at: '',
  updated_at: '',
};

function row(overrides: Partial<TrackingRow> = {}): TrackingRow {
  return {
    registration_id: 7,
    student: {
      id: 1, username: 'stu1', full_name: 'Stu One',
      university_registration_number: '1AY22MC001', department: 'MCA',
    },
    event: { id: 3, title: 'Tech Fest', event_date: '2026-09-01', venue: 'Hall', status: 'COMPLETED' },
    registration_status: 'REGISTERED',
    registered_at: '',
    participation_id: null,
    participation_status: null,
    live_capture_status: 'NOT_SUBMITTED',
    live_capture_submitted_at: null,
    live_capture_location: null,
    verification_status: 'NOT_APPLICABLE',
    certificate_status: 'NOT_ELIGIBLE',
    certificate_attempts_used: 0,
    certificate_attempts_remaining: 0,
    attendance_status: 'NOT_RECORDED',
    attendance_is_manual: false,
    attendance_decided_by: null,
    ...overrides,
  };
}

describe('EventCoordinatorTrackingComponent', () => {
  let tracking: jasmine.SpyObj<TrackingService>;
  let attendance: jasmine.SpyObj<AttendanceService>;
  let events: jasmine.SpyObj<EventService>;

  beforeEach(async () => {
    tracking = jasmine.createSpyObj<TrackingService>('TrackingService', ['list', 'forStudent']);
    attendance = jasmine.createSpyObj<AttendanceService>('AttendanceService', ['mark']);
    events = jasmine.createSpyObj<EventService>('EventService', ['list']);

    tracking.list.and.returnValue(of(page([row()])));
    events.list.and.returnValue(of(page([])));

    await TestBed.configureTestingModule({
      imports: [EventCoordinatorTrackingComponent],
      providers: [
        provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: TrackingService, useValue: tracking },
        { provide: AttendanceService, useValue: attendance },
        { provide: EventService, useValue: events },
      ],
    }).compileComponents();
  });

  function render() {
    const fixture = TestBed.createComponent(EventCoordinatorTrackingComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('shows a student who never captured as not submitted', () => {
    const fixture = render();
    expect(fixture.nativeElement.textContent).toContain('Not submitted');
    expect(fixture.componentInstance.liveCaptureLabel(row())).toBe('Not submitted');
  });

  it('shows the captured location where one is known', () => {
    tracking.list.and.returnValue(of(page([row({
      live_capture_status: 'SUBMITTED',
      live_capture_location: '12, Example Road (GPS accurate to 8 m)',
    })])));

    const fixture = render();
    expect(fixture.nativeElement.textContent).toContain('12, Example Road');
  });

  it('records attendance for a student with no participation', () => {
    attendance.mark.and.returnValue(of(MARKED));
    const fixture = render();

    fixture.componentInstance.markAttendance(row(), 'APPROVED');
    expect(attendance.mark).toHaveBeenCalledWith(7, 'APPROVED', '');
  });

  it('does not mark a student absent without a reason', () => {
    spyOn(window, 'prompt').and.returnValue('  ');
    const fixture = render();

    fixture.componentInstance.markAttendance(row(), 'REJECTED');
    expect(attendance.mark).not.toHaveBeenCalled();
  });

  it('sends the reason given when marking a student absent', () => {
    spyOn(window, 'prompt').and.returnValue('Did not attend');
    attendance.mark.and.returnValue(of(MARKED));
    const fixture = render();

    fixture.componentInstance.markAttendance(row(), 'REJECTED');
    expect(attendance.mark).toHaveBeenCalledWith(7, 'REJECTED', 'Did not attend');
  });

  it('drops empty filters instead of sending blanks', () => {
    const fixture = render();
    fixture.componentInstance.filters = {
      event: null, search: '', live_capture_status: 'NOT_SUBMITTED',
      verification_status: '', certificate_status: '', attendance_status: '',
    };
    fixture.componentInstance.load();

    expect(tracking.list).toHaveBeenCalledWith(
      jasmine.objectContaining({ live_capture_status: 'NOT_SUBMITTED' }),
    );
  });

  it('prefers the full name but falls back to the username', () => {
    const component = render().componentInstance;
    expect(component.displayName(row())).toBe('Stu One');
    expect(component.displayName(row({
      student: {
        id: 1, username: 'stu1', full_name: '',
        university_registration_number: null, department: null,
      },
    }))).toBe('stu1');
  });
});
