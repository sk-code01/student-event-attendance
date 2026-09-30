import { TestBed } from '@angular/core/testing';

import { CameraError, CameraService } from './camera.service';

describe('CameraService', () => {
  let service: CameraService;
  let originalMediaDevices: MediaDevices | undefined;
  let originalIsSecureContext: boolean;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CameraService);
    originalMediaDevices = navigator.mediaDevices;
    originalIsSecureContext = window.isSecureContext;
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'mediaDevices', { value: originalMediaDevices, configurable: true });
    Object.defineProperty(window, 'isSecureContext', { value: originalIsSecureContext, configurable: true });
  });

  function fakeVideoElement(): HTMLVideoElement {
    const video = document.createElement('video');
    spyOn(video, 'play').and.returnValue(Promise.resolve());
    return video;
  }

  it('throws insecure-context error outside a secure context', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    await expectAsync(service.start(fakeVideoElement())).toBeRejectedWith(
      jasmine.objectContaining({ code: 'insecure-context' } as Partial<CameraError>),
    );
  });

  it('throws unsupported error when getUserMedia is unavailable', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
    await expectAsync(service.start(fakeVideoElement())).toBeRejectedWith(
      jasmine.objectContaining({ code: 'unsupported' } as Partial<CameraError>),
    );
  });

  it('maps NotAllowedError to permission-denied', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: () => Promise.reject(new DOMException('denied', 'NotAllowedError')) },
      configurable: true,
    });
    await expectAsync(service.start(fakeVideoElement())).toBeRejectedWith(
      jasmine.objectContaining({ code: 'permission-denied' } as Partial<CameraError>),
    );
  });

  it('maps NotFoundError to no-camera', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: () => Promise.reject(new DOMException('none', 'NotFoundError')) },
      configurable: true,
    });
    await expectAsync(service.start(fakeVideoElement())).toBeRejectedWith(
      jasmine.objectContaining({ code: 'no-camera' } as Partial<CameraError>),
    );
  });

  it('starts successfully and marks isActive true, stop() releases tracks', async () => {
    // Real Chrome type-checks `video.srcObject` against an actual
    // MediaStream — a canvas-captured stream gives us a genuine
    // MediaStream with a real, stoppable track, without needing camera
    // hardware in the test environment.
    const canvas = document.createElement('canvas');
    const realStream = canvas.captureStream();
    const track = realStream.getTracks()[0];
    const stopSpy = spyOn(track, 'stop').and.callThrough();

    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: () => Promise.resolve(realStream) },
      configurable: true,
    });

    const video = fakeVideoElement();
    await service.start(video);
    expect(service.isActive).toBeTrue();
    expect(video.srcObject).toBe(realStream);

    service.stop();
    expect(stopSpy).toHaveBeenCalled();
    expect(service.isActive).toBeFalse();
  });

  it('captureFrame resolves a JPEG Blob from the video frame', async () => {
    const video = fakeVideoElement();
    Object.defineProperty(video, 'videoWidth', { value: 100 });
    Object.defineProperty(video, 'videoHeight', { value: 100 });

    const blob = await service.captureFrame(video);
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe('image/jpeg');
  });
});
