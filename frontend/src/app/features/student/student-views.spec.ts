import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { StudentAchievementsComponent } from './achievements/student-achievements.component';
import { StudentAttendanceComponent } from './attendance/student-attendance.component';
import { StudentOdComponent } from './od/student-od.component';
import { Achievement } from '../../core/models/achievement.model';
import { Attendance } from '../../core/models/attendance.model';
import { ODRequest } from '../../core/models/od.model';
import { AchievementService } from '../../core/services/achievement.service';
import { AttendanceService } from '../../core/services/attendance.service';
import { OdService } from '../../core/services/od.service';

const person = { id: 1, username: 'stu', role: 'STUDENT', department: 'CS' };
const staff = { id: 2, username: 'facultycs', role: 'FACULTY' };
const event = { id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall' };

const ATTENDANCE: Attendance = {
  id: 1, participation: 5, registration: 5, is_manual: false, student: person, event, status: 'REJECTED',
  requested_by: staff, requested_at: '2026-09-14T10:00:00Z',
  reviewed_by: { id: 3, username: 'hodcs', role: 'EVENT_COORDINATOR' }, reviewed_at: '2026-09-14T11:00:00Z',
  rejection_reason: 'Evidence insufficient', created_at: '', updated_at: '',
};

const OD: ODRequest = {
  id: 2, participation: 5, student: person, event, reason: 'Inter-college fest', status: 'APPROVED',
  requested_by: staff, requested_at: '2026-09-14T10:00:00Z',
  reviewed_by: { id: 3, username: 'hodcs', role: 'EVENT_COORDINATOR' }, reviewed_at: '2026-09-14T11:00:00Z',
  rejection_reason: '', created_at: '', updated_at: '',
};

function achievement(overrides: Partial<Achievement>): Achievement {
  return {
    id: 3, participation: 5, student: person, event,
    title: 'First Place', description: 'Won it', achievement_type: 'Competition',
    achievement_date: '2026-09-14', status: 'APPROVED', is_official: true,
    created_by: staff, reviewed_by: null, reviewed_at: null, rejection_reason: '',
    created_at: '', updated_at: '', ...overrides,
  };
}

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null });

describe('StudentAttendanceComponent', () => {
  let attendanceService: jasmine.SpyObj<AttendanceService>;

  beforeEach(async () => {
    attendanceService = jasmine.createSpyObj('AttendanceService', ['list']);
    await TestBed.configureTestingModule({
      imports: [StudentAttendanceComponent],
      providers: [provideRouter([]), { provide: AttendanceService, useValue: attendanceService }],
    }).compileComponents();
  });

  it('shows the status and rejection reason, and offers no approve control', () => {
    attendanceService.list.and.returnValue(of(page([ATTENDANCE])));
    const fixture = TestBed.createComponent(StudentAttendanceComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('REJECTED');
    expect(text).toContain('Evidence insufficient');
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
  });

  it('shows an empty state', () => {
    attendanceService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(StudentAttendanceComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No attendance records yet.');
  });

  it('shows an error state when loading fails', () => {
    attendanceService.list.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(StudentAttendanceComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });
});

describe('StudentOdComponent', () => {
  let odService: jasmine.SpyObj<OdService>;

  beforeEach(async () => {
    odService = jasmine.createSpyObj('OdService', ['list']);
    await TestBed.configureTestingModule({
      imports: [StudentOdComponent],
      providers: [provideRouter([]), { provide: OdService, useValue: odService }],
    }).compileComponents();
  });

  it('shows the requested reason and the decision', () => {
    odService.list.and.returnValue(of(page([OD])));
    const fixture = TestBed.createComponent(StudentOdComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Inter-college fest');
    expect(text).toContain('APPROVED');
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
  });

  it('shows an error state when loading fails', () => {
    odService.list.and.returnValue(throwError(() => ({ status: 403 })));
    const fixture = TestBed.createComponent(StudentOdComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });
});

describe('StudentAchievementsComponent', () => {
  let achievementService: jasmine.SpyObj<AchievementService>;

  beforeEach(async () => {
    achievementService = jasmine.createSpyObj('AchievementService', ['list']);
    await TestBed.configureTestingModule({
      imports: [StudentAchievementsComponent],
      providers: [provideRouter([]), { provide: AchievementService, useValue: achievementService }],
    }).compileComponents();
  });

  it('separates official achievements from pending and rejected ones', () => {
    achievementService.list.and.returnValue(
      of(
        page([
          achievement({ id: 1, title: 'Official Win', status: 'APPROVED', is_official: true }),
          achievement({ id: 2, title: 'Waiting', status: 'PENDING_APPROVAL', is_official: false }),
          achievement({ id: 3, title: 'Refused', status: 'REJECTED', is_official: false, rejection_reason: 'nope' }),
        ]),
      ),
    );
    const fixture = TestBed.createComponent(StudentAchievementsComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.official().map((a) => a.title)).toEqual(['Official Win']);
    expect(component.unofficial().map((a) => a.title)).toEqual(['Waiting', 'Refused']);

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Official achievements');
    expect(text).toContain('Not yet official');
    expect(text).toContain('nope');
    // A student never gets an edit or approve control over an official record.
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
  });

  it('shows an empty official list when nothing is approved', () => {
    achievementService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(StudentAchievementsComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No official achievements yet.');
  });
});
