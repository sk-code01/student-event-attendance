import { TestBed } from '@angular/core/testing';

import { GeoError, GeolocationService } from './geolocation.service';

describe('GeolocationService', () => {
  let service: GeolocationService;
  let originalGeolocation: Geolocation;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GeolocationService);
    originalGeolocation = navigator.geolocation;
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'geolocation', { value: originalGeolocation, configurable: true });
  });

  it('resolves latitude/longitude/accuracy on success', async () => {
    Object.defineProperty(navigator, 'geolocation', {
      value: {
        getCurrentPosition: (success: PositionCallback) =>
          success({
            coords: { latitude: 12.97, longitude: 77.59, accuracy: 15 },
            timestamp: Date.now(),
          } as GeolocationPosition),
      },
      configurable: true,
    });

    const result = await service.getCurrentPosition();
    expect(result.latitude).toBe(12.97);
    expect(result.longitude).toBe(77.59);
    expect(result.accuracy).toBe(15);
  });

  it('maps PERMISSION_DENIED to a typed GeoError', async () => {
    Object.defineProperty(navigator, 'geolocation', {
      value: {
        getCurrentPosition: (_success: PositionCallback, error: PositionErrorCallback) =>
          error({ code: 1, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError),
      },
      configurable: true,
    });

    await expectAsync(service.getCurrentPosition()).toBeRejectedWith(
      jasmine.objectContaining({ code: 'permission-denied' } as Partial<GeoError>),
    );
  });

  it('maps POSITION_UNAVAILABLE to a typed GeoError', async () => {
    Object.defineProperty(navigator, 'geolocation', {
      value: {
        getCurrentPosition: (_success: PositionCallback, error: PositionErrorCallback) =>
          error({ code: 2, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError),
      },
      configurable: true,
    });

    await expectAsync(service.getCurrentPosition()).toBeRejectedWith(
      jasmine.objectContaining({ code: 'unavailable' } as Partial<GeoError>),
    );
  });

  it('rejects with unsupported when geolocation API is absent', async () => {
    Object.defineProperty(navigator, 'geolocation', { value: undefined, configurable: true });
    await expectAsync(service.getCurrentPosition()).toBeRejectedWith(
      jasmine.objectContaining({ code: 'unsupported' } as Partial<GeoError>),
    );
  });
});
