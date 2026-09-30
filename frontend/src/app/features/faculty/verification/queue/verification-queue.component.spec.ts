import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { VerificationQueueComponent } from './verification-queue.component';
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
      venue_distance: 300, location_warning: true, validation_status: 'VALID', created_at: '',
    }],
  }],
  created_at: '', updated_at: '',
};

describe('VerificationQueueComponent', () => {
  let evidenceService: jasmine.SpyObj<EvidenceService>;

  beforeEach(async () => {
    evidenceService = jasmine.createSpyObj('EvidenceService', ['list']);
    await TestBed.configureTestingModule({
      imports: [VerificationQueueComponent],
      providers: [provideRouter([]), { provide: EvidenceService, useValue: evidenceService }],
    }).compileComponents();
  });

  it('loads and displays the queue with a location warning badge', () => {
    evidenceService.list.and.returnValue(of({ results: [MOCK_EVIDENCE], count: 1, next: null, previous: null }));
    const fixture = TestBed.createComponent(VerificationQueueComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.loading()).toBeFalse();
    expect(fixture.componentInstance.evidenceList().length).toBe(1);
    expect(fixture.componentInstance.hasLocationWarning(MOCK_EVIDENCE)).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Tech Fest');
    expect(fixture.nativeElement.textContent).toContain('Off-venue');
  });

  it('shows an error message when the queue fails to load', () => {
    evidenceService.list.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(VerificationQueueComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });

  it('shows an empty state when there is nothing to review', () => {
    evidenceService.list.and.returnValue(of({ results: [], count: 0, next: null, previous: null }));
    const fixture = TestBed.createComponent(VerificationQueueComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('No evidence has been submitted for review yet');
  });
});
