import { Injectable } from '@angular/core';

export type CameraErrorCode = 'unsupported' | 'insecure-context' | 'permission-denied' | 'no-camera' | 'in-use' | 'unknown';

export class CameraError extends Error {
  constructor(public readonly code: CameraErrorCode, message: string) {
    super(message);
  }
}

/**
 * Thin wrapper around the real browser camera APIs
 * (navigator.mediaDevices.getUserMedia + <canvas> frame capture). There is
 * no fallback/mock path here — if the browser or context doesn't support
 * it, callers receive a CameraError describing exactly why, and the UI is
 * responsible for explaining that to the student. Mocking only ever
 * happens inside automated tests, never in this class.
 */
@Injectable({ providedIn: 'root' })
export class CameraService {
  private stream: MediaStream | null = null;

  get isActive(): boolean {
    return this.stream !== null;
  }

  async start(videoElement: HTMLVideoElement): Promise<void> {
    if (!window.isSecureContext) {
      throw new CameraError('insecure-context', 'Camera access requires a secure connection (HTTPS or localhost).');
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new CameraError('unsupported', 'This browser does not support camera access.');
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
    } catch (error) {
      throw this.mapError(error);
    }

    videoElement.srcObject = this.stream;
    await videoElement.play();
  }

  /** Captures the current video frame as a still-image Blob. Only a single
   * still frame is ever captured — this never uploads/streams video. */
  captureFrame(videoElement: HTMLVideoElement): Promise<Blob> {
    const canvas = document.createElement('canvas');
    canvas.width = videoElement.videoWidth;
    canvas.height = videoElement.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) {
      return Promise.reject(new CameraError('unknown', 'Unable to capture the image.'));
    }
    context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new CameraError('unknown', 'Unable to capture the image.'))),
        'image/jpeg',
        0.9,
      );
    });
  }

  /** Stops all tracks and releases the camera. Must be called on retake
   * (before restarting), on submission, and on navigation away from the
   * capture page — leaving a MediaStream running is both a privacy issue
   * and keeps the browser's camera-in-use indicator lit unnecessarily. */
  stop(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  private mapError(error: unknown): CameraError {
    const name = error instanceof DOMException ? error.name : '';
    switch (name) {
      case 'NotAllowedError':
      case 'SecurityError':
        return new CameraError('permission-denied', 'Camera access was denied.');
      case 'NotFoundError':
        return new CameraError('no-camera', 'No camera was found on this device.');
      case 'NotReadableError':
      case 'TrackStartError':
        return new CameraError('in-use', 'The camera is already in use by another application.');
      default:
        return new CameraError('unknown', 'Unable to access the camera.');
    }
  }
}
