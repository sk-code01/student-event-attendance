import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { EventCoordinatorAchievementsComponent } from './achievements/event-coordinator-achievements.component';
import { EventCoordinatorAttendanceComponent } from './attendance/event-coordinator-attendance.component';
import { EventCoordinatorOdComponent } from './od/event-coordinator-od.component';
import { Achievement } from '../../core/models/achievement.model';
import { Attendance } from '../../core/models/attendance.model';
import { ODRequest } from '../../core/models/od.model';
import { AchievementService } from '../../core/services/achievement.service';
import { AttendanceService } from '../../core/services/attendance.service';
import { OdService } from '../../core/services/od.service';

const student = { id: 1, username: 'stu', role: 'STUDENT', department: 'CS' };
const faculty = { id: 2, username: 'facultycs', role: 'FACULTY' };
const eventCoordinator = { id: 3, username: 'hodcs', role: 'EVENT_COORDINATOR' };
const event = { id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall' };

const PENDING_ATTENDANCE: Attendance = {
  id: 11, participation: 5, registration: 5, is_manual: false, student, event, status: 'PENDING',
  requested_by: faculty, requested_at: '2026-09-14T10:00:00Z',
  reviewed_by: null, reviewed_at: null, rejection_reason: '', created_at: '', updated_at: '',
};

const PENDING_OD: ODRequest = { ...PENDING_ATTENDANCE, id: 12, reason: 'Fest' } as ODRequest;

const PENDING_ACHIEVEMENT: Achievement = {
  id: 13, participation: 5, student, event,
  title: 'First Place', description: '', achievement_type: 'Competition',
  achievement_date: '2026-09-14', status: 'PENDING_APPROVAL', is_official: false,
  created_by: faculty, reviewed_by: null, reviewed_at: null, rejection_reason: '',
  created_at: '', updated_at: '',
};

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null });

describe('EventCoordinatorAttendanceComponent', () => {
  let attendanceService: jasmine.SpyObj<AttendanceService>;

  beforeEach(async () => {
    attendanceService = jasmine.createSpyObj('AttendanceService', ['list', 'approve', 'reject']);
    await TestBed.configureTestingModule({
      imports: [EventCoordinatorAttendanceComponent],
      providers: [provideRouter([]), { provide: AttendanceService, useValue: attendanceService }],
    }).compileComponents();
  });

  it('splits pending requests from decided ones', () => {
    attendanceService.list.and.returnValue(
      of(page([PENDING_ATTENDANCE, { ...PENDING_ATTENDANCE, id: 14, status: 'APPROVED' as const }])),
    );
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.pending().map((r) => r.id)).toEqual([11]);
    expect(fixture.componentInstance.decided().map((r) => r.id)).toEqual([14]);
  });

  it('approves and replaces the row in place without a full reload', () => {
    attendanceService.list.and.returnValue(of(page([PENDING_ATTENDANCE])));
    attendanceService.approve.and.returnValue(
      of({ ...PENDING_ATTENDANCE, status: 'APPROVED' as const, reviewed_by: eventCoordinator, reviewed_at: '2026-09-14T11:00:00Z' }),
    );
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();

    fixture.componentInstance.approve(PENDING_ATTENDANCE);
    fixture.detectChanges();

    expect(attendanceService.approve).toHaveBeenCalledWith(11);
    expect(attendanceService.list).toHaveBeenCalledTimes(1);
    expect(fixture.componentInstance.pending().length).toBe(0);
    expect(fixture.componentInstance.decided()[0].status).toBe('APPROVED');
  });

  it('refuses to reject without a reason', () => {
    attendanceService.list.and.returnValue(of(page([PENDING_ATTENDANCE])));
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.startReject(PENDING_ATTENDANCE);
    component.rejectionReason = '  ';
    component.confirmReject(PENDING_ATTENDANCE);

    expect(attendanceService.reject).not.toHaveBeenCalled();
  });

  it('rejects with a trimmed reason', () => {
    attendanceService.list.and.returnValue(of(page([PENDING_ATTENDANCE])));
    attendanceService.reject.and.returnValue(
      of({ ...PENDING_ATTENDANCE, status: 'REJECTED' as const, rejection_reason: 'no', reviewed_by: eventCoordinator }),
    );
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.startReject(PENDING_ATTENDANCE);
    component.rejectionReason = '  no  ';
    component.confirmReject(PENDING_ATTENDANCE);
    fixture.detectChanges();

    expect(attendanceService.reject).toHaveBeenCalledWith(11, 'no');
    expect(component.decided()[0].rejection_reason).toBe('no');
  });

  it('ignores a second click while a decision is in flight', () => {
    attendanceService.list.and.returnValue(of(page([PENDING_ATTENDANCE])));
    attendanceService.approve.and.returnValue(throwError(() => ({ status: 400, error: {} })));
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.actioningId.set(11);
    component.approve(PENDING_ATTENDANCE);
    expect(attendanceService.approve).not.toHaveBeenCalled();
  });

  it('surfaces a backend error message on a failed decision', () => {
    attendanceService.list.and.returnValue(of(page([PENDING_ATTENDANCE])));
    attendanceService.approve.and.returnValue(
      throwError(() => ({ error: { detail: 'This attendance request has already been approved.' } })),
    );
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();

    fixture.componentInstance.approve(PENDING_ATTENDANCE);
    expect(fixture.componentInstance.errorMessage()).toContain('already been approved');
  });

  it('shows an error state when the queue cannot be loaded', () => {
    attendanceService.list.and.returnValue(throwError(() => ({ status: 403 })));
    const fixture = TestBed.createComponent(EventCoordinatorAttendanceComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });
});

describe('EventCoordinatorOdComponent', () => {
  let odService: jasmine.SpyObj<OdService>;

  beforeEach(async () => {
    odService = jasmine.createSpyObj('OdService', ['list', 'approve', 'reject']);
    await TestBed.configureTestingModule({
      imports: [EventCoordinatorOdComponent],
      providers: [provideRouter([]), { provide: OdService, useValue: odService }],
    }).compileComponents();
  });

  it('shows the requested reason and approves independently of attendance', () => {
    odService.list.and.returnValue(of(page([PENDING_OD])));
    odService.approve.and.returnValue(of({ ...PENDING_OD, status: 'APPROVED' as const, reviewed_by: eventCoordinator }));
    const fixture = TestBed.createComponent(EventCoordinatorOdComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Fest');
    fixture.componentInstance.approve(PENDING_OD);
    fixture.detectChanges();

    expect(odService.approve).toHaveBeenCalledWith(12);
    expect(fixture.componentInstance.decided()[0].status).toBe('APPROVED');
  });

  it('requires a reason to reject', () => {
    odService.list.and.returnValue(of(page([PENDING_OD])));
    const fixture = TestBed.createComponent(EventCoordinatorOdComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.startReject(PENDING_OD);
    component.rejectionReason = '';
    component.confirmReject(PENDING_OD);
    expect(odService.reject).not.toHaveBeenCalled();
  });

  it('shows an empty state', () => {
    odService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(EventCoordinatorOdComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No on-duty requests are waiting on your decision');
  });
});

describe('EventCoordinatorAchievementsComponent', () => {
  let achievementService: jasmine.SpyObj<AchievementService>;

  beforeEach(async () => {
    achievementService = jasmine.createSpyObj('AchievementService', ['list', 'approve', 'reject']);
    await TestBed.configureTestingModule({
      imports: [EventCoordinatorAchievementsComponent],
      providers: [provideRouter([]), { provide: AchievementService, useValue: achievementService }],
    }).compileComponents();
  });

  it('only queues PENDING_APPROVAL records for decision, not drafts', () => {
    achievementService.list.and.returnValue(
      of(
        page([
          PENDING_ACHIEVEMENT,
          { ...PENDING_ACHIEVEMENT, id: 20, status: 'DRAFT' as const },
          { ...PENDING_ACHIEVEMENT, id: 21, status: 'APPROVED' as const, is_official: true },
        ]),
      ),
    );
    const fixture = TestBed.createComponent(EventCoordinatorAchievementsComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.pending().map((r) => r.id)).toEqual([13]);
    expect(fixture.componentInstance.decided().map((r) => r.id)).toEqual([21]);
  });

  it('approves an achievement and moves it to the decided list', () => {
    achievementService.list.and.returnValue(of(page([PENDING_ACHIEVEMENT])));
    achievementService.approve.and.returnValue(
      of({ ...PENDING_ACHIEVEMENT, status: 'APPROVED' as const, is_official: true, reviewed_by: eventCoordinator }),
    );
    const fixture = TestBed.createComponent(EventCoordinatorAchievementsComponent);
    fixture.detectChanges();

    fixture.componentInstance.approve(PENDING_ACHIEVEMENT);
    fixture.detectChanges();

    expect(achievementService.approve).toHaveBeenCalledWith(13);
    expect(fixture.componentInstance.decided()[0].is_official).toBeTrue();
  });

  it('requires a reason to reject', () => {
    achievementService.list.and.returnValue(of(page([PENDING_ACHIEVEMENT])));
    const fixture = TestBed.createComponent(EventCoordinatorAchievementsComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.startReject(PENDING_ACHIEVEMENT);
    component.rejectionReason = '   ';
    component.confirmReject(PENDING_ACHIEVEMENT);
    expect(achievementService.reject).not.toHaveBeenCalled();
  });
});
