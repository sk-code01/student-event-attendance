import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { LiveCaptureComponent } from './live-capture.component';
import { CameraError, CameraService } from '../../../core/services/camera.service';
import { EvidenceService } from '../../../core/services/evidence.service';
import { EventService } from '../../../core/services/event.service';
import { GeoError, GeolocationService } from '../../../core/services/geolocation.service';
import { OfflineCaptureQueueService } from '../../../core/services/offline-capture-queue.service';
import { ParticipationService } from '../../../core/services/participation.service';
import { Evidence } from '../../../core/models/evidence.model';
import { Event } from '../../../core/models/event.model';
import { Participation } from '../../../core/models/participation.model';

const MOCK_EVENT: Event = {
  id: 1, title: 'Tech Fest', description: '', event_date: '2026-09-13', venue: 'Hall',
  venue_latitude: null, venue_longitude: null, category: 'Technical',
  conducting_college: { id: 1, name: 'Engineering College', code: 'ENGG', is_active: true, created_at: '', updated_at: '' },
  created_by: { id: 2, username: 'hodcs' }, status: 'PUBLISHED',
  registration_start_date: '2026-09-01', registration_end_date: '2026-09-12',
  is_registration_open: false, my_registration_status: 'REGISTERED', created_at: '', updated_at: '',
};

describe('LiveCaptureComponent', () => {
  let cameraService: jasmine.SpyObj<CameraService>;
  let geolocationService: jasmine.SpyObj<GeolocationService>;
  let participationService: jasmine.SpyObj<ParticipationService>;
  let evidenceService: jasmine.SpyObj<EvidenceService>;
  let offlineQueue: jasmine.SpyObj<OfflineCaptureQueueService>;
  let eventService: jasmine.SpyObj<EventService>;

  beforeEach(async () => {
    cameraService = jasmine.createSpyObj('CameraService', ['start', 'captureFrame', 'stop']);
    geolocationService = jasmine.createSpyObj('GeolocationService', ['getCurrentPosition']);
    participationService = jasmine.createSpyObj('ParticipationService', ['checkEligibility', 'open', 'get']);
    evidenceService = jasmine.createSpyObj('EvidenceService', ['submitCaptureSession', 'get']);
    offlineQueue = jasmine.createSpyObj('OfflineCaptureQueueService', ['enqueue']);
    eventService = jasmine.createSpyObj('EventService', ['get']);

    eventService.get.and.returnValue(of(MOCK_EVENT));
    participationService.open.and.returnValue(of({ id: 42 } as Participation));
    cameraService.start.and.returnValue(Promise.resolve());
    cameraService.captureFrame.and.returnValue(Promise.resolve(new Blob(['x'], { type: 'image/jpeg' })));
    geolocationService.getCurrentPosition.and.returnValue(
      Promise.resolve({ latitude: 12.9, longitude: 77.5, accuracy: 15, timestamp: Date.now() }),
    );

    await TestBed.configureTestingModule({
      imports: [LiveCaptureComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: '1' }), data: {} } } },
        { provide: CameraService, useValue: cameraService },
        { provide: GeolocationService, useValue: geolocationService },
        { provide: ParticipationService, useValue: participationService },
        { provide: EvidenceService, useValue: evidenceService },
        { provide: OfflineCaptureQueueService, useValue: offlineQueue },
        { provide: EventService, useValue: eventService },
      ],
    }).compileComponents();
  });

  function createFixture(eligible = true, reason: string | null = null) {
    participationService.checkEligibility.and.returnValue(
      of({ eligible, reason, max_gps_accuracy_meters: 50 }),
    );
    const fixture = TestBed.createComponent(LiveCaptureComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('shows NOT_ELIGIBLE with the reason when the student is not eligible', () => {
    const fixture = createFixture(false, 'Participation is only available on the event date.');
    fixture.detectChanges();
    expect(fixture.componentInstance.state()).toBe('NOT_ELIGIBLE');
    expect(fixture.nativeElement.textContent).toContain('only available on the event date');
  });

  it('progresses through camera and location setup to READY_TO_CAPTURE when eligible', async () => {
    const fixture = createFixture(true);
    await fixture.whenStable();
    expect(cameraService.start).toHaveBeenCalled();
    expect(geolocationService.getCurrentPosition).toHaveBeenCalled();
    expect(fixture.componentInstance.state()).toBe('READY_TO_CAPTURE');
    expect(fixture.componentInstance.gpsAccuracy()).toBe(15);
  });

  it('enters ERROR state with a friendly message when camera permission is denied', async () => {
    cameraService.start.and.returnValue(Promise.reject(new CameraError('permission-denied', 'denied')));
    const fixture = createFixture(true);
    await fixture.whenStable();
    expect(fixture.componentInstance.state()).toBe('ERROR');
    expect(fixture.componentInstance.errorMessage()).toContain('denied');
    expect(geolocationService.getCurrentPosition).not.toHaveBeenCalled();
  });

  it('enters ERROR state and blocks submission when location permission is denied', async () => {
    geolocationService.getCurrentPosition.and.returnValue(Promise.reject(new GeoError('permission-denied', 'denied')));
    const fixture = createFixture(true);
    await fixture.whenStable();
    expect(fixture.componentInstance.state()).toBe('ERROR');
    expect(fixture.componentInstance.errorMessage()).toContain('cannot proceed without it');
    // No submit path exists to reach from ERROR — there is no bypass button.
    expect(fixture.nativeElement.querySelector('button.btn-success')).toBeNull();
  });

  it('captures, allows retake, then confirms the primary capture into the review list', async () => {
    const fixture = createFixture(true);
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    expect(component.state()).toBe('CAPTURE_PREVIEW');

    component.retake();
    expect(component.state()).toBe('READY_TO_CAPTURE');
    expect(component.pendingPrimary()).toBeNull();

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();

    expect(component.state()).toBe('REVIEW');
    expect(component.pendingPrimary()).not.toBeNull();
  });

  it('supports capturing additional images after the primary', async () => {
    const fixture = createFixture(true);
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();
    expect(component.state()).toBe('REVIEW');

    component.captureAnother();
    expect(component.state()).toBe('READY_TO_CAPTURE');

    component.captureImage('ADDITIONAL');
    await fixture.whenStable();
    component.confirmCapture();

    expect(component.pendingAdditional().length).toBe(1);
    expect(component.state()).toBe('REVIEW');
  });

  it('submits online via participationService.open then evidenceService.submitCaptureSession', async () => {
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    evidenceService.submitCaptureSession.and.returnValue(Promise.resolve({ status: 'SUBMITTED' } as Evidence));

    const fixture = createFixture(true);
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();

    await component.submit();
    expect(participationService.open).toHaveBeenCalledWith(1);
    expect(evidenceService.submitCaptureSession).toHaveBeenCalledWith(42, jasmine.any(Array));
    expect(offlineQueue.enqueue).not.toHaveBeenCalled();
    expect(component.state()).toBe('SUBMITTED');
    expect(cameraService.stop).toHaveBeenCalled();
  });

  it('queues offline instead of calling the API when offline at submit time', async () => {
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    offlineQueue.enqueue.and.returnValue(Promise.resolve());

    const fixture = createFixture(true);
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();

    await component.submit();
    expect(offlineQueue.enqueue).toHaveBeenCalled();
    expect(evidenceService.submitCaptureSession).not.toHaveBeenCalled();
    expect(component.state()).toBe('OFFLINE_QUEUED');

    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  it('falls back to the offline queue when the online submission fails with a network error', async () => {
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    evidenceService.submitCaptureSession.and.returnValue(Promise.reject({ status: 0 }));
    offlineQueue.enqueue.and.returnValue(Promise.resolve());

    const fixture = createFixture(true);
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();

    await component.submit();
    expect(offlineQueue.enqueue).toHaveBeenCalled();
    expect(component.state()).toBe('OFFLINE_QUEUED');
  });

  it('shows a validation error and stays on REVIEW when submission fails with a 400', async () => {
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    evidenceService.submitCaptureSession.and.returnValue(
      Promise.reject({ status: 400, error: { event: ['Registration is not currently open for this event.'] } }),
    );

    const fixture = createFixture(true);
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();

    await component.submit();
    expect(component.state()).toBe('REVIEW');
    expect(component.errorMessage()).toContain('not currently open');
  });

  it('stops the camera on component destruction', async () => {
    const fixture = createFixture(true);
    await fixture.whenStable();
    fixture.destroy();
    expect(cameraService.stop).toHaveBeenCalled();
  });
});

describe('LiveCaptureComponent (resubmission mode)', () => {
  let cameraService: jasmine.SpyObj<CameraService>;
  let geolocationService: jasmine.SpyObj<GeolocationService>;
  let participationService: jasmine.SpyObj<ParticipationService>;
  let evidenceService: jasmine.SpyObj<EvidenceService>;
  let offlineQueue: jasmine.SpyObj<OfflineCaptureQueueService>;
  let eventService: jasmine.SpyObj<EventService>;

  const MOCK_PARTICIPATION: Participation = {
    id: 7, registration: 1, student: { id: 1, username: 'stu', email: '' },
    event: { id: 1, title: 'Tech Fest', event_date: '2026-09-13', venue: 'Hall', status: 'PUBLISHED' },
    status: 'SUBMITTED', evidence_id: 55, evidence_status: 'RESUBMISSION_REQUIRED',
    submitted_at: '2026-09-13T10:00:00Z', created_at: '', updated_at: '',
  };

  const MOCK_EVIDENCE: Evidence = {
    id: 55, participation: 7,
    student: { id: 1, username: 'stu', full_name: 'Test Student', university_registration_number: '1AY22MC001', email: '', department: 'CS' },
    event: { id: 1, title: 'Tech Fest', event_date: '2026-09-13', venue: 'Hall', category: 'Technical', status: 'PUBLISHED', college: 'ENGG' },
    status: 'RESUBMISSION_REQUIRED', current_version_number: 1,
    versions: [{
      id: 100, version_number: 1, submitted_by: 1, submission_reason: '', submitted_at: '2026-09-13T10:00:00Z',
      created_at: '', captures: [], has_primary_capture: true, effective_decision: 'RESUBMISSION_REQUIRED',
      in_progress: false,
      verifications: [{ id: 1, reviewer: { id: 2, username: 'facultycs', role: 'FACULTY' }, decision: 'RESUBMISSION_REQUIRED', reason: 'Face not visible', is_event_coordinator_override: false, created_at: '' }],
    }],
    created_at: '', updated_at: '',
  };

  beforeEach(async () => {
    cameraService = jasmine.createSpyObj('CameraService', ['start', 'captureFrame', 'stop']);
    geolocationService = jasmine.createSpyObj('GeolocationService', ['getCurrentPosition']);
    participationService = jasmine.createSpyObj('ParticipationService', ['checkEligibility', 'open', 'get']);
    evidenceService = jasmine.createSpyObj('EvidenceService', ['submitCaptureSession', 'get']);
    offlineQueue = jasmine.createSpyObj('OfflineCaptureQueueService', ['enqueue']);
    eventService = jasmine.createSpyObj('EventService', ['get']);

    participationService.get.and.returnValue(of(MOCK_PARTICIPATION));
    participationService.checkEligibility.and.returnValue(of({ eligible: false, reason: null, max_gps_accuracy_meters: 50 }));
    evidenceService.get.and.returnValue(of(MOCK_EVIDENCE));
    cameraService.start.and.returnValue(Promise.resolve());
    cameraService.captureFrame.and.returnValue(Promise.resolve(new Blob(['x'], { type: 'image/jpeg' })));
    geolocationService.getCurrentPosition.and.returnValue(
      Promise.resolve({ latitude: 12.9, longitude: 77.5, accuracy: 15, timestamp: Date.now() }),
    );

    await TestBed.configureTestingModule({
      imports: [LiveCaptureComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: '7' }), data: { mode: 'resubmit' } } } },
        { provide: CameraService, useValue: cameraService },
        { provide: GeolocationService, useValue: geolocationService },
        { provide: ParticipationService, useValue: participationService },
        { provide: EvidenceService, useValue: evidenceService },
        { provide: OfflineCaptureQueueService, useValue: offlineQueue },
        { provide: EventService, useValue: eventService },
      ],
    }).compileComponents();
  });

  it('skips the participation eligibility gate and shows the Faculty reason', async () => {
    // checkEligibility IS still called in resubmit mode, but only to read its
    // max_gps_accuracy_meters config value for the GPS badge — its
    // eligible/reason fields (which would say "already submitted") are
    // deliberately never used to gate resubmission.
    const fixture = TestBed.createComponent(LiveCaptureComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.componentInstance.state()).toBe('READY_TO_CAPTURE');
    expect(fixture.componentInstance.resubmissionReason()).toBe('Face not visible');
  });

  it('blocks resubmission when evidence status is not RESUBMISSION_REQUIRED', async () => {
    evidenceService.get.and.returnValue(of({ ...MOCK_EVIDENCE, status: 'VERIFIED' } as Evidence));
    const fixture = TestBed.createComponent(LiveCaptureComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fixture.componentInstance.state()).toBe('NOT_ELIGIBLE');
  });

  it('submits directly against the existing participation id, without reopening one', async () => {
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    evidenceService.submitCaptureSession.and.returnValue(Promise.resolve({ status: 'SUBMITTED' } as Evidence));

    const fixture = TestBed.createComponent(LiveCaptureComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;

    component.captureImage('PRIMARY');
    await fixture.whenStable();
    component.confirmCapture();

    await component.submit();
    expect(participationService.open).not.toHaveBeenCalled();
    expect(evidenceService.submitCaptureSession).toHaveBeenCalledWith(7, jasmine.any(Array));
    expect(component.state()).toBe('SUBMITTED');
  });
});
