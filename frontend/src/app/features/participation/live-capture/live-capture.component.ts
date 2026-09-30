import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, ViewChild, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { CameraError, CameraService } from '../../../core/services/camera.service';
import { EvidenceService } from '../../../core/services/evidence.service';
import { EventService } from '../../../core/services/event.service';
import { GeoError, GeolocationService } from '../../../core/services/geolocation.service';
import { OfflineCaptureQueueService } from '../../../core/services/offline-capture-queue.service';
import { ParticipationService } from '../../../core/services/participation.service';
import { CaptureRole, PendingEvidenceCapture } from '../../../core/models/evidence.model';
import { EligibilityResult } from '../../../core/models/participation.model';

type CaptureState =
  | 'CHECKING_ELIGIBILITY'
  | 'NOT_ELIGIBLE'
  | 'CAMERA_PERMISSION_REQUIRED'
  | 'LOCATION_PERMISSION_REQUIRED'
  | 'LOCATION_ACQUIRING'
  | 'READY_TO_CAPTURE'
  | 'CAPTURE_PREVIEW'
  | 'REVIEW'
  | 'SUBMITTING'
  | 'SUBMITTED'
  | 'OFFLINE_QUEUED'
  | 'ERROR';

type CaptureMode = 'INITIAL' | 'RESUBMIT';

@Component({
  selector: 'app-live-capture',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './live-capture.component.html',
})
export class LiveCaptureComponent implements OnInit, OnDestroy {
  @ViewChild('video') videoRef?: ElementRef<HTMLVideoElement>;

  readonly state = signal<CaptureState>('CHECKING_ELIGIBILITY');
  readonly eligibility = signal<EligibilityResult | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly gpsAccuracy = signal<number | null>(null);
  readonly gpsPosition = signal<{ latitude: number; longitude: number; accuracy: number } | null>(null);
  readonly pendingPrimary = signal<PendingEvidenceCapture | null>(null);
  readonly pendingAdditional = signal<PendingEvidenceCapture[]>([]);
  readonly currentPreview = signal<PendingEvidenceCapture | null>(null);
  readonly resubmissionReason = signal<string | null>(null);
  private currentRoleBeingCaptured: CaptureRole = 'PRIMARY';

  protected mode: CaptureMode = 'INITIAL';
  protected eventId!: number;
  protected participationId: number | null = null;
  private eventTitle = '';
  readonly eventTitleSignal = signal('');

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly cameraService: CameraService,
    private readonly geolocationService: GeolocationService,
    private readonly participationService: ParticipationService,
    private readonly evidenceService: EvidenceService,
    private readonly offlineQueue: OfflineCaptureQueueService,
    private readonly eventService: EventService,
  ) {}

  ngOnInit(): void {
    this.mode = this.route.snapshot.data['mode'] === 'resubmit' ? 'RESUBMIT' : 'INITIAL';
    if (this.mode === 'RESUBMIT') {
      this.participationId = Number(this.route.snapshot.paramMap.get('id'));
      this.checkResubmissionEligibilityThenStart();
    } else {
      this.eventId = Number(this.route.snapshot.paramMap.get('id'));
      this.eventService.get(this.eventId).subscribe({
        next: (event) => {
          this.eventTitle = event.title;
          this.eventTitleSignal.set(event.title);
        },
      });
      this.checkEligibilityThenStart();
    }
  }

  ngOnDestroy(): void {
    this.cameraService.stop();
    this.releasePreviewUrls();
  }

  private checkEligibilityThenStart(): void {
    this.state.set('CHECKING_ELIGIBILITY');
    this.participationService.checkEligibility(this.eventId).subscribe({
      next: (result) => {
        this.eligibility.set(result);
        if (!result.eligible) {
          this.state.set('NOT_ELIGIBLE');
          return;
        }
        this.beginCameraSetup();
      },
      error: () => {
        this.errorMessage.set('Unable to check eligibility. Please check your connection and try again.');
        this.state.set('ERROR');
      },
    });
  }

  /** Resubmission skips the normal Participation eligibility check (the
   * Participation is already SUBMITTED) — instead it requires the current
   * evidence status to actually be RESUBMISSION_REQUIRED, confirmed
   * server-side just like everything else here. */
  private checkResubmissionEligibilityThenStart(): void {
    this.state.set('CHECKING_ELIGIBILITY');
    this.participationService.get(this.participationId!).subscribe({
      next: (participation) => {
        this.eventId = participation.event.id;
        this.eventTitle = participation.event.title;
        this.eventTitleSignal.set(participation.event.title);

        if (!participation.evidence_id) {
          this.eligibility.set({ eligible: false, reason: 'No evidence has been submitted for this participation yet.', max_gps_accuracy_meters: 50 });
          this.state.set('NOT_ELIGIBLE');
          return;
        }

        this.evidenceService.get(participation.evidence_id).subscribe({
          next: (evidence) => {
            if (evidence.status !== 'RESUBMISSION_REQUIRED') {
              this.eligibility.set({
                eligible: false,
                reason: 'A new submission is not required for this participation right now.',
                max_gps_accuracy_meters: 50,
              });
              this.state.set('NOT_ELIGIBLE');
              return;
            }
            const currentVersion = evidence.versions[evidence.versions.length - 1];
            const latestVerification = currentVersion?.verifications[currentVersion.verifications.length - 1];
            this.resubmissionReason.set(latestVerification?.reason ?? null);
            // Only used here for its max_gps_accuracy_meters config value (for
            // the GPS-accuracy badge) — its eligible/reason fields don't apply
            // to resubmission and are intentionally ignored.
            this.participationService.checkEligibility(this.eventId).subscribe({
              next: (result) => this.eligibility.update((current) => ({ ...current!, max_gps_accuracy_meters: result.max_gps_accuracy_meters })),
              error: () => undefined,
            });
            this.eligibility.set({ eligible: true, reason: null, max_gps_accuracy_meters: 50 });
            this.beginCameraSetup();
          },
          error: () => {
            this.errorMessage.set('Unable to check evidence status. Please check your connection and try again.');
            this.state.set('ERROR');
          },
        });
      },
      error: () => {
        this.errorMessage.set('Unable to load this participation. Please check your connection and try again.');
        this.state.set('ERROR');
      },
    });
  }

  private async beginCameraSetup(): Promise<void> {
    this.state.set('CAMERA_PERMISSION_REQUIRED');
    await this.waitForNextRender();
    const video = this.videoRef?.nativeElement;
    if (!video) {
      this.errorMessage.set('Unable to initialize the camera view.');
      this.state.set('ERROR');
      return;
    }

    try {
      await this.cameraService.start(video);
    } catch (error) {
      this.errorMessage.set(this.describeCameraError(error));
      this.state.set('ERROR');
      return;
    }

    await this.acquireLocation();
  }

  private async acquireLocation(): Promise<void> {
    this.state.set('LOCATION_PERMISSION_REQUIRED');
    await this.waitForNextRender();
    this.state.set('LOCATION_ACQUIRING');

    try {
      const position = await this.geolocationService.getCurrentPosition();
      this.gpsAccuracy.set(position.accuracy);
      this.gpsPosition.set(position);
      this.state.set('READY_TO_CAPTURE');
    } catch (error) {
      this.errorMessage.set(this.describeGeoError(error));
      this.state.set('ERROR');
    }
  }

  captureImage(role: CaptureRole): void {
    const video = this.videoRef?.nativeElement;
    const position = this.gpsPosition();
    if (!video || !position) return;

    this.currentRoleBeingCaptured = role;
    this.cameraService.captureFrame(video).then((blob) => {
      const capture: PendingEvidenceCapture = {
        role,
        blob,
        previewUrl: URL.createObjectURL(blob),
        deviceCaptureTimestamp: new Date().toISOString(),
        latitude: position.latitude,
        longitude: position.longitude,
        gpsAccuracy: position.accuracy,
      };
      this.currentPreview.set(capture);
      this.state.set('CAPTURE_PREVIEW');
    });
  }

  retake(): void {
    const preview = this.currentPreview();
    if (preview) URL.revokeObjectURL(preview.previewUrl);
    this.currentPreview.set(null);
    this.state.set('READY_TO_CAPTURE');
  }

  confirmCapture(): void {
    const preview = this.currentPreview();
    if (!preview) return;

    if (preview.role === 'PRIMARY') {
      this.pendingPrimary.set(preview);
    } else {
      this.pendingAdditional.update((list) => [...list, preview]);
    }
    this.currentPreview.set(null);
    this.state.set('REVIEW');
  }

  captureAnother(): void {
    this.state.set('READY_TO_CAPTURE');
  }

  removeAdditional(index: number): void {
    this.pendingAdditional.update((list) => {
      URL.revokeObjectURL(list[index].previewUrl);
      return list.filter((_, i) => i !== index);
    });
  }

  async submit(): Promise<void> {
    const primary = this.pendingPrimary();
    if (!primary) return;

    this.state.set('SUBMITTING');
    this.errorMessage.set(null);
    const allCaptures = [primary, ...this.pendingAdditional()];

    if (!navigator.onLine) {
      await this.offlineQueue.enqueue({
        eventId: this.eventId, eventTitle: this.eventTitle, captures: allCaptures,
        participationId: this.mode === 'RESUBMIT' ? this.participationId! : undefined,
      });
      this.cameraService.stop();
      this.state.set('OFFLINE_QUEUED');
      return;
    }

    try {
      const participationId = this.mode === 'RESUBMIT'
        ? this.participationId!
        : (await firstValueFrom(this.participationService.open(this.eventId))).id;
      await this.evidenceService.submitCaptureSession(participationId, allCaptures);
      this.cameraService.stop();
      this.state.set('SUBMITTED');
    } catch (error: unknown) {
      const httpError = error as { status?: number };
      if (httpError?.status === 0) {
        // Lost connectivity mid-submit — fall back to the offline queue
        // rather than losing the captures the student already took.
        await this.offlineQueue.enqueue({
          eventId: this.eventId, eventTitle: this.eventTitle, captures: allCaptures,
          participationId: this.mode === 'RESUBMIT' ? this.participationId! : undefined,
        });
        this.cameraService.stop();
        this.state.set('OFFLINE_QUEUED');
        return;
      }
      this.errorMessage.set(this.describeSubmitError(error));
      this.state.set('REVIEW');
    }
  }

  goToEvent(): void {
    this.router.navigate(['/student/events', this.eventId]);
  }

  private describeCameraError(error: unknown): string {
    if (error instanceof CameraError) {
      switch (error.code) {
        case 'permission-denied': return 'Camera access was denied. Please allow camera access and try again.';
        case 'no-camera': return 'No camera was found on this device.';
        case 'in-use': return 'The camera is already in use by another application.';
        case 'insecure-context': return 'Camera access requires a secure (HTTPS) connection.';
        case 'unsupported': return 'This browser does not support camera access.';
        default: return 'Unable to access the camera.';
      }
    }
    return 'Unable to access the camera.';
  }

  private describeGeoError(error: unknown): string {
    if (error instanceof GeoError) {
      switch (error.code) {
        case 'permission-denied': return 'Location access was denied. Location is required to submit participation — submission cannot proceed without it.';
        case 'unavailable': return 'Your location could not be determined. Submission cannot proceed without it.';
        case 'timeout': return 'Getting your location took too long. Please try again.';
        case 'unsupported': return 'This browser does not support location access.';
        default: return 'Unable to determine your location.';
      }
    }
    return 'Unable to determine your location.';
  }

  private describeSubmitError(error: unknown): string {
    const httpError = error as { status?: number; error?: Record<string, unknown> };
    if (httpError?.error && typeof httpError.error === 'object') {
      const firstKey = Object.keys(httpError.error)[0];
      const value = firstKey ? (httpError.error as Record<string, unknown>)[firstKey] : null;
      if (value) return Array.isArray(value) ? String(value[0]) : String(value);
    }
    return 'Submission failed. Please try again.';
  }

  private releasePreviewUrls(): void {
    this.pendingPrimary()?.previewUrl && URL.revokeObjectURL(this.pendingPrimary()!.previewUrl);
    this.pendingAdditional().forEach((c) => URL.revokeObjectURL(c.previewUrl));
    this.currentPreview()?.previewUrl && URL.revokeObjectURL(this.currentPreview()!.previewUrl);
  }

  private waitForNextRender(): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, 0));
  }
}
