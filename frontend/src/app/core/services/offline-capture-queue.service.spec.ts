import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { AuthService } from './auth.service';
import { EvidenceService } from './evidence.service';
import { OfflineCaptureQueueService } from './offline-capture-queue.service';
import { ParticipationService } from './participation.service';
import { PendingEvidenceCapture } from '../models/evidence.model';

describe('OfflineCaptureQueueService', () => {
  let service: OfflineCaptureQueueService;
  let participationService: jasmine.SpyObj<ParticipationService>;
  let evidenceService: jasmine.SpyObj<EvidenceService>;

  const fakeCapture: PendingEvidenceCapture = {
    role: 'PRIMARY', blob: new Blob(['x'], { type: 'image/jpeg' }), previewUrl: '',
    deviceCaptureTimestamp: '2026-09-13T12:00:00Z', latitude: 12.9, longitude: 77.5, gpsAccuracy: 10,
  };

  async function clearDatabase(svc: OfflineCaptureQueueService) {
    const sessions = await svc.listForCurrentUser();
    for (const session of sessions) {
      await svc.discard(session.id);
    }
  }

  beforeEach(async () => {
    const participationSpy = jasmine.createSpyObj('ParticipationService', ['open']);
    const evidenceSpy = jasmine.createSpyObj('EvidenceService', ['submitCaptureSession']);
    participationSpy.open.and.returnValue(of({ id: 99 }));

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ParticipationService, useValue: participationSpy },
        { provide: EvidenceService, useValue: evidenceSpy },
      ],
    });

    service = TestBed.inject(OfflineCaptureQueueService);
    participationService = TestBed.inject(ParticipationService) as jasmine.SpyObj<ParticipationService>;
    evidenceService = TestBed.inject(EvidenceService) as jasmine.SpyObj<EvidenceService>;

    const authService = TestBed.inject(AuthService);
    spyOn(authService, 'currentUser').and.returnValue({
      id: 1, username: 'student1', email: '', full_name: 'Student One', role: 'STUDENT',
      university_registration_number: null, faculty_id: null,
      department: null, is_active: true, date_joined: '',
    });

    await clearDatabase(service);
  });

  afterEach(async () => {
    await clearDatabase(service);
  });

  it('enqueues a session and lists it for the current user', async () => {
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });
    const sessions = await service.listForCurrentUser();
    expect(sessions.length).toBe(1);
    expect(sessions[0].eventId).toBe(5);
    expect(sessions[0].status).toBe('PENDING');
  });

  it('updates the pendingCount signal on enqueue', async () => {
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });
    expect(service.pendingCount()).toBe(1);
  });

  it('removes a session from the queue on successful sync, opening a participation first when none was queued', async () => {
    evidenceService.submitCaptureSession.and.returnValue(Promise.resolve({} as never));
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });

    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    await service.syncAll();

    expect(participationService.open).toHaveBeenCalledWith(5);
    expect(evidenceService.submitCaptureSession).toHaveBeenCalledWith(99, jasmine.any(Array));
    const sessions = await service.listForCurrentUser();
    expect(sessions.length).toBe(0);
  });

  it('a queued resubmission (with a known participationId) skips opening a fresh participation', async () => {
    evidenceService.submitCaptureSession.and.returnValue(Promise.resolve({} as never));
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture], participationId: 42 });

    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    await service.syncAll();

    expect(participationService.open).not.toHaveBeenCalled();
    expect(evidenceService.submitCaptureSession).toHaveBeenCalledWith(42, jasmine.any(Array));
  });

  it('marks a session FAILED on a permanent (4xx) validation error, without retrying forever', async () => {
    evidenceService.submitCaptureSession.and.returnValue(
      Promise.reject({ status: 400, error: { detail: 'Bad capture' } }),
    );
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });

    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    await service.syncAll();

    const sessions = await service.listForCurrentUser();
    expect(sessions.length).toBe(1);
    expect(sessions[0].status).toBe('FAILED');
    expect(sessions[0].lastError).toContain('Bad capture');
  });

  it('keeps a session PENDING (for retry) on a network/5xx failure', async () => {
    evidenceService.submitCaptureSession.and.returnValue(Promise.reject({ status: 0 }));
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });

    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    await service.syncAll();

    const sessions = await service.listForCurrentUser();
    expect(sessions.length).toBe(1);
    expect(sessions[0].status).toBe('PENDING');
  });

  it('does not attempt to sync while offline', async () => {
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    await service.syncAll();
    expect(evidenceService.submitCaptureSession).not.toHaveBeenCalled();
  });

  it('discard removes a session regardless of status', async () => {
    await service.enqueue({ eventId: 5, eventTitle: 'Test Event', captures: [fakeCapture] });
    const [session] = await service.listForCurrentUser();
    await service.discard(session.id);
    expect((await service.listForCurrentUser()).length).toBe(0);
  });
});
