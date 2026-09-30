import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { VerificationDetailComponent } from './verification-detail.component';
import { EvidenceService } from '../../../../core/services/evidence.service';
import { Evidence } from '../../../../core/models/evidence.model';

const MOCK_EVIDENCE: Evidence = {
  id: 1, participation: 1,
  student: { id: 1, username: 'stu', full_name: 'Test Student', university_registration_number: '1AY22MC001', email: '', department: 'CS' },
  event: { id: 1, title: 'Tech Fest', event_date: '2026-09-13', venue: 'Hall', category: 'Technical', status: 'PUBLISHED', college: 'ENGG' },
  status: 'SUBMITTED', current_version_number: 1,
  versions: [{
    id: 10, version_number: 1, submitted_by: 1, submission_reason: '', submitted_at: '2026-09-13T10:00:00Z',
    created_at: '', has_primary_capture: true, effective_decision: null, in_progress: false, verifications: [],
    captures: [{
      id: 100, capture_role: 'PRIMARY', image_url: '/img', mime_type: 'image/jpeg', file_size: 1, sha256_hash: 'a',
      device_capture_timestamp: '', server_received_timestamp: '', latitude: '1', longitude: '1', gps_accuracy: 10,
      venue_distance: null, location_warning: false, validation_status: 'VALID', created_at: '',
    }],
  }],
  created_at: '', updated_at: '',
};

describe('VerificationDetailComponent', () => {
  let evidenceService: jasmine.SpyObj<EvidenceService>;

  beforeEach(async () => {
    evidenceService = jasmine.createSpyObj('EvidenceService', ['get', 'verify', 'reject', 'requestResubmission']);
    evidenceService.get.and.returnValue(of(MOCK_EVIDENCE));

    await TestBed.configureTestingModule({
      imports: [VerificationDetailComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: '1' }) } } },
        { provide: EvidenceService, useValue: evidenceService },
      ],
    }).compileComponents();
  });

  it('loads and displays the evidence with decision controls visible for SUBMITTED status', () => {
    const fixture = TestBed.createComponent(VerificationDetailComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.canDecide()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Verify');
    expect(fixture.nativeElement.textContent).toContain('Reject');
    expect(fixture.nativeElement.textContent).toContain('Request Resubmission');
  });

  it('rejecting without a reason shows a validation error and does not call the API', () => {
    const fixture = TestBed.createComponent(VerificationDetailComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.startAction('REJECT');
    component.reason = '   ';
    component.confirmAction();

    expect(component.errorMessage()).toContain('reason is required');
    expect(evidenceService.reject).not.toHaveBeenCalled();
  });

  it('verifying without a reason is allowed (optional for VERIFIED)', () => {
    evidenceService.verify.and.returnValue(of({ ...MOCK_EVIDENCE, status: 'VERIFIED' }));
    const fixture = TestBed.createComponent(VerificationDetailComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.startAction('VERIFY');
    component.confirmAction();

    expect(evidenceService.verify).toHaveBeenCalledWith(1, '');
    expect(component.evidence()?.status).toBe('VERIFIED');
  });

  it('reject with a reason calls the API and updates the evidence', () => {
    evidenceService.reject.and.returnValue(of({ ...MOCK_EVIDENCE, status: 'REJECTED' }));
    const fixture = TestBed.createComponent(VerificationDetailComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.startAction('REJECT');
    component.reason = 'blurry image';
    component.confirmAction();

    expect(evidenceService.reject).toHaveBeenCalledWith(1, 'blurry image');
    expect(component.evidence()?.status).toBe('REJECTED');
  });

  it('hides decision controls once a decision already exists (VERIFIED)', () => {
    evidenceService.get.and.returnValue(of({ ...MOCK_EVIDENCE, status: 'VERIFIED' }));
    const fixture = TestBed.createComponent(VerificationDetailComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.canDecide()).toBeFalse();
  });

  it('shows a server error message when the decision call fails', () => {
    evidenceService.reject.and.returnValue(throwError(() => ({ error: { detail: 'Already decided.' } })));
    const fixture = TestBed.createComponent(VerificationDetailComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    component.startAction('REJECT');
    component.reason = 'test';
    component.confirmAction();

    expect(component.errorMessage()).toContain('Already decided.');
  });
});
