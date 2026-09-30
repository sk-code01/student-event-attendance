import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AdminAchievementsComponent } from './admin-achievements.component';
import { AdminAttendanceComponent } from './admin-attendance.component';
import { AdminOdComponent } from './admin-od.component';
import { Achievement } from '../../../core/models/achievement.model';
import { Attendance } from '../../../core/models/attendance.model';
import { ODRequest } from '../../../core/models/od.model';
import { AchievementService } from '../../../core/services/achievement.service';
import { AttendanceService } from '../../../core/services/attendance.service';
import { OdService } from '../../../core/services/od.service';

const student = { id: 1, username: 'stu', role: 'STUDENT', department: 'CS' };
const faculty = { id: 2, username: 'facultycs', role: 'FACULTY' };
const event = { id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall' };

const ATTENDANCE: Attendance = {
  id: 1, participation: 5, registration: 5, is_manual: false, student, event, status: 'APPROVED',
  requested_by: faculty, requested_at: '', reviewed_by: { id: 3, username: 'hodcs', role: 'EVENT_COORDINATOR' },
  reviewed_at: '', rejection_reason: '', created_at: '', updated_at: '',
};

const OD: ODRequest = { ...ATTENDANCE, id: 2, reason: 'Fest', status: 'REJECTED', rejection_reason: 'nope' } as ODRequest;

const ACHIEVEMENT: Achievement = {
  id: 3, participation: 5, student, event, title: 'First Place', description: '',
  achievement_type: 'Competition', achievement_date: '2026-09-14', status: 'APPROVED', is_official: true,
  created_by: faculty, reviewed_by: { id: 3, username: 'hodcs', role: 'EVENT_COORDINATOR' }, reviewed_at: '',
  rejection_reason: '', created_at: '', updated_at: '',
};

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null });

describe('AdminAttendanceComponent', () => {
  let attendanceService: jasmine.SpyObj<AttendanceService>;

  beforeEach(async () => {
    attendanceService = jasmine.createSpyObj('AttendanceService', ['list']);
    await TestBed.configureTestingModule({
      imports: [AdminAttendanceComponent],
      providers: [provideRouter([]), { provide: AttendanceService, useValue: attendanceService }],
    }).compileComponents();
  });

  it('renders records read-only with no decision controls', () => {
    attendanceService.list.and.returnValue(of(page([ATTENDANCE])));
    const fixture = TestBed.createComponent(AdminAttendanceComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('APPROVED');
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
  });

  it('shows an error state', () => {
    attendanceService.list.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(AdminAttendanceComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });
});

describe('AdminOdComponent', () => {
  let odService: jasmine.SpyObj<OdService>;

  beforeEach(async () => {
    odService = jasmine.createSpyObj('OdService', ['list']);
    await TestBed.configureTestingModule({
      imports: [AdminOdComponent],
      providers: [provideRouter([]), { provide: OdService, useValue: odService }],
    }).compileComponents();
  });

  it('renders OD records read-only including the rejection reason', () => {
    odService.list.and.returnValue(of(page([OD])));
    const fixture = TestBed.createComponent(AdminOdComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('nope');
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
  });

  it('shows an empty state', () => {
    odService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(AdminOdComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No OD requests yet.');
  });
});

describe('AdminAchievementsComponent', () => {
  let achievementService: jasmine.SpyObj<AchievementService>;

  beforeEach(async () => {
    achievementService = jasmine.createSpyObj('AchievementService', ['list']);
    await TestBed.configureTestingModule({
      imports: [AdminAchievementsComponent],
      providers: [provideRouter([]), { provide: AchievementService, useValue: achievementService }],
    }).compileComponents();
  });

  it('renders achievements read-only with no approve controls', () => {
    achievementService.list.and.returnValue(of(page([ACHIEVEMENT])));
    const fixture = TestBed.createComponent(AdminAchievementsComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('First Place');
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
  });
});
