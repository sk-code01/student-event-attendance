import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { EventCoordinatorVerificationDetailComponent } from './event-coordinator-verification-detail.component';
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

describe('EventCoordinatorVerificationDetailComponent', () => {
  let evidenceService: jasmine.SpyObj<EvidenceService>;

  beforeEach(async () => {
    evidenceService = jasmine.createSpyObj('EvidenceService', ['get', 'override']);
    evidenceService.get.and.returnValue(of(MOCK_EVIDENCE));

    await TestBed.configureTestingModule({
      imports: [EventCoordinatorVerificationDetailComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: '1' }) } } },
        { provide: EvidenceService, useValue: evidenceService },
      ],
    }).compileComponents();
  });

  it('shows the Faculty decision and an Override button', () => {
    const fixture = TestBed.createComponent(EventCoordinatorVerificationDetailComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.facultyDecision()?.decision).toBe('REJECTED');
    expect(fixture.componentInstance.canOverride()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Override Faculty Decision');
  });

  it('does not offer an override when there is no Faculty decision yet', () => {
    evidenceService.get.and.returnValue(of({ ...MOCK_EVIDENCE, versions: [{ ...MOCK_EVIDENCE.versions[0], verifications: [] }] }));
    const fixture = TestBed.createComponent(EventCoordinatorVerificationDetailComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.canOverride()).toBeFalse();
  });

  it('override without a reason shows a validation error', () => {
    const fixture = TestBed.createComponent(EventCoordinatorVerificationDetailComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.startOverride();
    component.overrideReason = '  ';
    component.confirmOverride();

    expect(component.errorMessage()).toContain('reason is required');
    expect(evidenceService.override).not.toHaveBeenCalled();
  });

  it('override with a decision and reason calls the API and preserves the Faculty decision in history', () => {
    evidenceService.override.and.returnValue(of({
      ...MOCK_EVIDENCE,
      status: 'VERIFIED',
      versions: [{
        ...MOCK_EVIDENCE.versions[0],
        verifications: [
          ...MOCK_EVIDENCE.versions[0].verifications,
          { id: 2, reviewer: { id: 3, username: 'hodcs', role: 'EVENT_COORDINATOR' }, decision: 'VERIFIED', reason: 'reviewed personally', is_event_coordinator_override: true, created_at: '' },
        ],
      }],
    }));
    const fixture = TestBed.createComponent(EventCoordinatorVerificationDetailComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.startOverride();
    component.overrideDecision = 'VERIFIED';
    component.overrideReason = 'reviewed personally';
    component.confirmOverride();

    expect(evidenceService.override).toHaveBeenCalledWith(1, 'VERIFIED', 'reviewed personally');
    expect(component.evidence()?.status).toBe('VERIFIED');
    expect(component.facultyDecision()?.decision).toBe('REJECTED');
    expect(component.hodOverrides().length).toBe(1);
  });
});
