import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AuthService } from '../../core/services/auth.service';
import { CertificateService } from '../../core/services/certificate.service';
import { TrackingService } from '../../core/services/tracking.service';
import { Certificate } from '../../core/models/certificate.model';
import { TrackingRow } from '../../core/models/tracking.model';
import { User } from '../../core/models/user.model';
import { CertificateReviewComponent } from './certificate-review.component';
import { MyCertificatesComponent } from './my-certificates.component';

function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results };
}

const STUDENT: User = {
  id: 1, username: 'stu1', email: 'stu1@example.com', full_name: 'Stu One',
  university_registration_number: '1AY22MC001', faculty_id: null,
  role: 'STUDENT', department: null, is_active: true, date_joined: '',
} as User;

function row(overrides: Partial<TrackingRow> = {}): TrackingRow {
  return {
    registration_id: 7,
    student: {
      id: 1, username: 'stu1', full_name: 'Stu One',
      university_registration_number: '1AY22MC001', department: 'MCA',
    },
    event: { id: 3, title: 'Tech Fest', event_date: '2026-09-01', venue: 'Hall', status: 'COMPLETED' },
    registration_status: 'REGISTERED',
    registered_at: '',
    participation_id: 11,
    participation_status: 'SUBMITTED',
    live_capture_status: 'SUBMITTED',
    live_capture_submitted_at: '',
    live_capture_location: '12, Example Road (GPS accurate to 8 m)',
    verification_status: 'VERIFIED',
    certificate_status: 'NOT_SUBMITTED',
    certificate_attempts_used: 0,
    certificate_attempts_remaining: 3,
    attendance_status: 'NOT_RECORDED',
    attendance_is_manual: false,
    attendance_decided_by: null,
    ...overrides,
  };
}

function certificate(overrides: Partial<Certificate> = {}): Certificate {
  return {
    id: 5,
    participation: 11,
    attempt_number: 1,
    status: 'SUBMITTED',
    original_filename: 'cert.pdf',
    mime_type: 'application/pdf',
    file_size: 100,
    student: { id: 1, username: 'stu1', role: 'STUDENT', department: 'MCA' },
    event: { id: 3, title: 'Tech Fest', event_date: '2026-09-01' },
    submitted_at: '',
    reviewed_by: null,
    reviewed_at: null,
    rejection_reason: '',
    final_decision: '',
    final_decided_by: null,
    final_decided_at: null,
    final_rejection_reason: '',
    awaits_final_decision: false,
    download_url: '/api/v1/certificates/5/file/',
    attempts_used: 1,
    attempts_remaining: 2,
    ...overrides,
  };
}

describe('MyCertificatesComponent', () => {
  let tracking: jasmine.SpyObj<TrackingService>;
  let certificates: jasmine.SpyObj<CertificateService>;

  beforeEach(async () => {
    tracking = jasmine.createSpyObj<TrackingService>('TrackingService', ['list', 'forStudent']);
    certificates = jasmine.createSpyObj<CertificateService>('CertificateService', ['list', 'upload']);
    tracking.list.and.returnValue(of(page([row()])));
    certificates.list.and.returnValue(of(page<Certificate>([])));

    await TestBed.configureTestingModule({
      imports: [MyCertificatesComponent],
      providers: [
        provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: TrackingService, useValue: tracking },
        { provide: CertificateService, useValue: certificates },
      ],
    }).compileComponents();
  });

  function render() {
    const fixture = TestBed.createComponent(MyCertificatesComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('offers upload only when the window is open and attempts remain', () => {
    const component = render().componentInstance;

    expect(component.canUpload(row({ certificate_status: 'NOT_SUBMITTED' }))).toBeTrue();
    expect(component.canUpload(row({ certificate_status: 'REJECTED' }))).toBeTrue();
    expect(component.canUpload(row({ certificate_status: 'WINDOW_NOT_OPEN' }))).toBeFalse();
    expect(component.canUpload(row({ certificate_status: 'SUBMITTED' }))).toBeFalse();
    expect(component.canUpload(row({ certificate_status: 'VERIFIED' }))).toBeFalse();
  });

  it('does not offer upload when the student never captured', () => {
    const component = render().componentInstance;
    expect(component.canUpload(row({
      certificate_status: 'NOT_ELIGIBLE', participation_id: null,
    }))).toBeFalse();
  });

  it('does not offer a fourth attempt', () => {
    const component = render().componentInstance;
    expect(component.canUpload(row({
      certificate_status: 'REJECTED', certificate_attempts_used: 3, certificate_attempts_remaining: 0,
    }))).toBeFalse();
  });

  it('explains why the window is shut rather than just disabling the button', () => {
    const component = render().componentInstance;
    expect(component.statusLabel(row({ certificate_status: 'WINDOW_NOT_OPEN' })))
      .toContain('day after the event');
    expect(component.statusLabel(row({ certificate_status: 'NOT_ELIGIBLE' })))
      .toContain('no live capture');
  });

  it('shows the rejection reason the student has to act on', () => {
    certificates.list.and.returnValue(of(page([
      certificate({ status: 'REJECTED', rejection_reason: 'Name does not match' }),
    ])));
    tracking.list.and.returnValue(of(page([row({ certificate_status: 'REJECTED' })])));

    const fixture = render();
    expect(fixture.nativeElement.textContent).toContain('Name does not match');
  });
});

describe('CertificateReviewComponent', () => {
  let certificates: jasmine.SpyObj<CertificateService>;
  let auth: AuthService;

  function setUpAs(role: 'FACULTY' | 'EVENT_COORDINATOR', rows: Certificate[]) {
    certificates = jasmine.createSpyObj<CertificateService>(
      'CertificateService', ['list', 'decide', 'finalDecision', 'acceptExhausted'],
    );
    certificates.list.and.returnValue(of(page(rows)));

    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [CertificateReviewComponent],
      providers: [
        provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: CertificateService, useValue: certificates },
      ],
    });
    auth = TestBed.inject(AuthService);
    (auth as unknown as { _currentUser: { set(value: User): void } })._currentUser.set({
      ...STUDENT, role,
    } as User);

    const fixture = TestBed.createComponent(CertificateReviewComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('offers Faculty the verify decision on an undecided submission', () => {
    const component = setUpAs('FACULTY', [certificate()]).componentInstance;
    expect(component.awaitingVerification(certificate())).toBeTrue();
    // The final decision is the coordinator's, not theirs.
    expect(component.awaitingFinalDecision(certificate({ awaits_final_decision: true }))).toBeFalse();
  });

  it('offers the coordinator the final decision only after Faculty verified it', () => {
    const component = setUpAs('EVENT_COORDINATOR', [certificate()]).componentInstance;

    expect(component.awaitingFinalDecision(certificate({
      status: 'VERIFIED', awaits_final_decision: true,
    }))).toBeTrue();
    expect(component.awaitingFinalDecision(certificate({
      status: 'SUBMITTED', awaits_final_decision: false,
    }))).toBeFalse();
    // And verification itself stays with Faculty.
    expect(component.awaitingVerification(certificate())).toBeFalse();
  });

  it('offers acceptance of a rejected certificate only once attempts are exhausted', () => {
    const component = setUpAs('EVENT_COORDINATOR', [certificate()]).componentInstance;

    expect(component.canAcceptExhausted(certificate({
      status: 'REJECTED', attempts_remaining: 0,
    }))).toBeTrue();
    expect(component.canAcceptExhausted(certificate({
      status: 'REJECTED', attempts_remaining: 1,
    }))).toBeFalse();
  });

  it('does not send a rejection without a reason', () => {
    const fixture = setUpAs('FACULTY', [certificate()]);
    spyOn(window, 'prompt').and.returnValue('   ');

    fixture.componentInstance.reject(certificate());
    expect(certificates.decide).not.toHaveBeenCalled();
  });

  it('sends the reason given with a rejection', () => {
    const fixture = setUpAs('FACULTY', [certificate()]);
    spyOn(window, 'prompt').and.returnValue('Illegible scan');
    certificates.decide.and.returnValue(of(certificate({ status: 'REJECTED' })));

    fixture.componentInstance.reject(certificate());
    expect(certificates.decide).toHaveBeenCalledWith(5, 'REJECTED', 'Illegible scan');
  });

  it('surfaces the server’s own message when an action is refused', () => {
    const fixture = setUpAs('EVENT_COORDINATOR', [certificate()]);
    certificates.finalDecision.and.returnValue(
      throwError(() => ({ error: { detail: 'A final decision has already been recorded.' } })),
    );

    fixture.componentInstance.finalAccept(certificate());
    expect(fixture.componentInstance.busyId()).toBeNull();
  });
});
