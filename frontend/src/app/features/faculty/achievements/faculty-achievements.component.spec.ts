import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { FacultyAchievementsComponent } from './faculty-achievements.component';
import { Achievement } from '../../../core/models/achievement.model';
import { Evidence } from '../../../core/models/evidence.model';
import { AchievementService } from '../../../core/services/achievement.service';
import { EvidenceService } from '../../../core/services/evidence.service';

function evidence(id: number, participation: number, status: Evidence['status']): Evidence {
  return {
    id, participation,
    student: { id: 1, username: 'stu', full_name: 'Test Student', university_registration_number: '1AY22MC001', email: '', department: 'CS' },
    event: {
      id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall',
      category: 'Technical', status: 'PUBLISHED', college: 'ENGG',
    },
    status, current_version_number: 1, versions: [], created_at: '', updated_at: '',
  };
}

const CREATED: Achievement = {
  id: 13, participation: 5,
  student: { id: 1, username: 'stu', role: 'STUDENT', department: 'CS' },
  event: { id: 1, title: 'Tech Fest', event_date: '2026-09-14', venue: 'Hall' },
  title: 'First Place', description: '', achievement_type: 'Competition',
  achievement_date: '2026-09-14', status: 'PENDING_APPROVAL', is_official: false,
  created_by: { id: 2, username: 'facultycs', role: 'FACULTY' },
  reviewed_by: null, reviewed_at: null, rejection_reason: '', created_at: '', updated_at: '',
};

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null });

describe('FacultyAchievementsComponent', () => {
  let achievementService: jasmine.SpyObj<AchievementService>;
  let evidenceService: jasmine.SpyObj<EvidenceService>;

  beforeEach(async () => {
    achievementService = jasmine.createSpyObj('AchievementService', ['list', 'create']);
    evidenceService = jasmine.createSpyObj('EvidenceService', ['list']);
    await TestBed.configureTestingModule({
      imports: [FacultyAchievementsComponent],
      providers: [
        provideRouter([]),
        { provide: AchievementService, useValue: achievementService },
        { provide: EvidenceService, useValue: evidenceService },
      ],
    }).compileComponents();
  });

  function setup(evidenceList: Evidence[] = [evidence(1, 5, 'VERIFIED')], achievements: Achievement[] = []) {
    evidenceService.list.and.returnValue(of(page(evidenceList)));
    achievementService.list.and.returnValue(of(page(achievements)));
    const fixture = TestBed.createComponent(FacultyAchievementsComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('offers only verified participations in the form', () => {
    const fixture = setup([evidence(1, 5, 'VERIFIED'), evidence(2, 6, 'SUBMITTED')]);
    expect(fixture.componentInstance.verifiedEvidence().map((e) => e.participation)).toEqual([5]);
  });

  it('will not submit an incomplete form', () => {
    const fixture = setup();
    fixture.componentInstance.create();
    expect(achievementService.create).not.toHaveBeenCalled();
    expect(fixture.componentInstance.form.invalid).toBeTrue();
  });

  it('creates an achievement without sending a status and reports the pending outcome', () => {
    const fixture = setup();
    achievementService.create.and.returnValue(of(CREATED));

    fixture.componentInstance.form.setValue({
      participation: 5,
      title: 'First Place',
      achievement_type: 'Competition',
      achievement_date: '2026-09-14',
      description: 'Won it',
    });
    fixture.componentInstance.create();
    fixture.detectChanges();

    const payload = achievementService.create.calls.mostRecent().args[0];
    expect(payload.participation).toBe(5);
    expect((payload as unknown as Record<string, unknown>)['status']).toBeUndefined();
    expect(fixture.componentInstance.successMessage()).toContain('submitted for Event Coordinator approval');
    expect(fixture.componentInstance.achievements()[0].id).toBe(13);
  });

  it('never renders an approve control for faculty', () => {
    const fixture = setup([evidence(1, 5, 'VERIFIED')], [CREATED]);
    expect(fixture.nativeElement.textContent).not.toContain('Approve');
  });

  it('surfaces a backend validation error', () => {
    const fixture = setup();
    achievementService.create.and.returnValue(
      throwError(() => ({ error: { achievement_date: ['Achievement date cannot be in the future.'] } })),
    );

    fixture.componentInstance.form.setValue({
      participation: 5, title: 'T', achievement_type: 'C', achievement_date: '2030-01-01', description: '',
    });
    fixture.componentInstance.create();

    expect(fixture.componentInstance.errorMessage()).toContain('cannot be in the future');
  });
});
