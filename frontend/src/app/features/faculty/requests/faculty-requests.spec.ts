import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { FacultyAttendanceRequestsComponent } from './faculty-attendance-requests.component';
import { FacultyOdRequestsComponent } from './faculty-od-requests.component';
import { Attendance } from '../../../core/models/attendance.model';
import { Evidence } from '../../../core/models/evidence.model';
import { ODRequest } from '../../../core/models/od.model';
import { AttendanceService } from '../../../core/services/attendance.service';
import { EvidenceService } from '../../../core/services/evidence.service';
import { OdService } from '../../../core/services/od.service';

function evidence(id: number, participation: number, status: Evidence['status'], username = 'stu'): Evidence {
  return {
    id, participation,
    student: {
      id: 1, username, full_name: 'Test Student',
      university_registration_number: '1AY22MC001', email: '', department: 'CS',
    },
    event: {
      id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall',
      category: 'Technical', status: 'PUBLISHED', college: 'ENGG',
    },
    status, current_version_number: 1, versions: [], created_at: '', updated_at: '',
  };
}

const ATTENDANCE: Attendance = {
  id: 11, participation: 5, registration: 5, is_manual: false,
  student: { id: 1, username: 'stu', role: 'STUDENT', department: 'CS' },
  event: { id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall' },
  status: 'PENDING',
  requested_by: { id: 2, username: 'facultycs', role: 'FACULTY' },
  requested_at: '2026-09-14T10:00:00Z',
  reviewed_by: null, reviewed_at: null, rejection_reason: '', created_at: '', updated_at: '',
};

const OD: ODRequest = { ...ATTENDANCE, id: 12, reason: 'Fest' } as ODRequest;

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null });

describe('FacultyAttendanceRequestsComponent', () => {
  let evidenceService: jasmine.SpyObj<EvidenceService>;
  let attendanceService: jasmine.SpyObj<AttendanceService>;

  beforeEach(async () => {
    evidenceService = jasmine.createSpyObj('EvidenceService', ['list']);
    attendanceService = jasmine.createSpyObj('AttendanceService', ['list', 'request']);
    await TestBed.configureTestingModule({
      imports: [FacultyAttendanceRequestsComponent],
      providers: [
        provideRouter([]),
        { provide: EvidenceService, useValue: evidenceService },
        { provide: AttendanceService, useValue: attendanceService },
      ],
    }).compileComponents();
  });

  it('lists only verified participations and joins any existing request', () => {
    evidenceService.list.and.returnValue(
      of(page([evidence(1, 5, 'VERIFIED'), evidence(2, 6, 'REJECTED'), evidence(3, 7, 'SUBMITTED')])),
    );
    attendanceService.list.and.returnValue(of(page([ATTENDANCE])));

    const fixture = TestBed.createComponent(FacultyAttendanceRequestsComponent);
    fixture.detectChanges();

    const rows = fixture.componentInstance.rows();
    expect(rows.length).toBe(1);
    expect(rows[0].evidence.participation).toBe(5);
    expect(rows[0].attendance?.status).toBe('PENDING');
    // Faculty never get an approve/reject control on this page.
    expect(fixture.nativeElement.textContent).not.toContain('Approve');
  });

  it('requests attendance and updates the row without a reload', () => {
    evidenceService.list.and.returnValue(of(page([evidence(1, 5, 'VERIFIED')])));
    attendanceService.list.and.returnValue(of(page([])));
    attendanceService.request.and.returnValue(of(ATTENDANCE));

    const fixture = TestBed.createComponent(FacultyAttendanceRequestsComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.rows()[0].attendance).toBeNull();
    fixture.componentInstance.request(fixture.componentInstance.rows()[0]);
    fixture.detectChanges();

    expect(attendanceService.request).toHaveBeenCalledWith(5);
    expect(fixture.componentInstance.rows()[0].attendance?.status).toBe('PENDING');
    expect(fixture.nativeElement.textContent).toContain('Awaiting Event Coordinator decision');
  });

  it('surfaces the backend validation message when a request is refused', () => {
    evidenceService.list.and.returnValue(of(page([evidence(1, 5, 'VERIFIED')])));
    attendanceService.list.and.returnValue(of(page([])));
    attendanceService.request.and.returnValue(
      throwError(() => ({ error: { detail: 'Attendance can only be requested for verified evidence.' } })),
    );

    const fixture = TestBed.createComponent(FacultyAttendanceRequestsComponent);
    fixture.detectChanges();
    fixture.componentInstance.request(fixture.componentInstance.rows()[0]);
    fixture.detectChanges();

    expect(fixture.componentInstance.errorMessage()).toContain('verified evidence');
  });

  it('shows an empty state when nothing is verified', () => {
    evidenceService.list.and.returnValue(of(page([evidence(1, 5, 'SUBMITTED')])));
    attendanceService.list.and.returnValue(of(page([])));

    const fixture = TestBed.createComponent(FacultyAttendanceRequestsComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Attendance can only be requested for verified participation');
  });
});

describe('FacultyOdRequestsComponent', () => {
  let evidenceService: jasmine.SpyObj<EvidenceService>;
  let odService: jasmine.SpyObj<OdService>;

  beforeEach(async () => {
    evidenceService = jasmine.createSpyObj('EvidenceService', ['list']);
    odService = jasmine.createSpyObj('OdService', ['list', 'request']);
    await TestBed.configureTestingModule({
      imports: [FacultyOdRequestsComponent],
      providers: [
        provideRouter([]),
        { provide: EvidenceService, useValue: evidenceService },
        { provide: OdService, useValue: odService },
      ],
    }).compileComponents();
  });

  it('will not submit an OD request without a reason', () => {
    evidenceService.list.and.returnValue(of(page([evidence(1, 5, 'VERIFIED')])));
    odService.list.and.returnValue(of(page([])));

    const fixture = TestBed.createComponent(FacultyOdRequestsComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.startRequest(component.rows()[0]);
    component.reason = '   ';
    component.confirmRequest(component.rows()[0]);

    expect(odService.request).not.toHaveBeenCalled();
  });

  it('submits a trimmed reason and updates the row', () => {
    evidenceService.list.and.returnValue(of(page([evidence(1, 5, 'VERIFIED')])));
    odService.list.and.returnValue(of(page([])));
    odService.request.and.returnValue(of(OD));

    const fixture = TestBed.createComponent(FacultyOdRequestsComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.startRequest(component.rows()[0]);
    component.reason = '  Inter-college fest  ';
    component.confirmRequest(component.rows()[0]);
    fixture.detectChanges();

    expect(odService.request).toHaveBeenCalledWith(5, 'Inter-college fest');
    expect(component.rows()[0].odRequest?.id).toBe(12);
  });

  it('shows an error when loading fails', () => {
    evidenceService.list.and.returnValue(throwError(() => ({ status: 500 })));
    odService.list.and.returnValue(of(page([])));

    const fixture = TestBed.createComponent(FacultyOdRequestsComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });
});
