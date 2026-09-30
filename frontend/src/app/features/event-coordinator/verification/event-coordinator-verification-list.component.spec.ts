import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { EventCoordinatorVerificationListComponent } from './event-coordinator-verification-list.component';
import { EvidenceService } from '../../../core/services/evidence.service';
import { Evidence } from '../../../core/models/evidence.model';

const MOCK_EVIDENCE: Evidence = {
  id: 1, participation: 1,
  student: { id: 1, username: 'stu', full_name: 'Test Student', university_registration_number: '1AY22MC001', email: '', department: 'CS' },
  event: { id: 1, title: 'Tech Fest', event_date: '2026-09-13', venue: 'Hall', category: 'Technical', status: 'PUBLISHED', college: 'ENGG' },
  status: 'REJECTED', current_version_number: 1,
  versions: [{
    id: 10, version_number: 1, submitted_by: 1, submission_reason: '', submitted_at: '2026-09-13T10:00:00Z',
    created_at: '', has_primary_capture: true, effective_decision: 'REJECTED', in_progress: false,
    verifications: [{ id: 1, reviewer: { id: 2, username: 'facultycs', role: 'FACULTY' }, decision: 'REJECTED', reason: 'blurry', is_event_coordinator_override: false, created_at: '' }],
    captures: [],
  }],
  created_at: '', updated_at: '',
};

describe('EventCoordinatorVerificationListComponent', () => {
  let evidenceService: jasmine.SpyObj<EvidenceService>;

  beforeEach(async () => {
    evidenceService = jasmine.createSpyObj('EvidenceService', ['list']);
    await TestBed.configureTestingModule({
      imports: [EventCoordinatorVerificationListComponent],
      providers: [provideRouter([]), { provide: EvidenceService, useValue: evidenceService }],
    }).compileComponents();
  });

  it('loads and displays department-scoped evidence', () => {
    evidenceService.list.and.returnValue(of({ results: [MOCK_EVIDENCE], count: 1, next: null, previous: null }));
    const fixture = TestBed.createComponent(EventCoordinatorVerificationListComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.evidenceList().length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('Tech Fest');
    expect(fixture.nativeElement.textContent).toContain('REJECTED');
  });
});
