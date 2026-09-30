import { Injectable } from '@angular/core';

export type GeoErrorCode = 'unsupported' | 'permission-denied' | 'unavailable' | 'timeout' | 'unknown';

export class GeoError extends Error {
  constructor(public readonly code: GeoErrorCode, message: string) {
    super(message);
  }
}

export interface GeoPosition {
  latitude: number;
  longitude: number;
  accuracy: number;
  timestamp: number;
}

/**
 * Thin wrapper around the real browser Geolocation API. Never fabricates
 * coordinates and never falls back to IP-based geolocation — if the
 * browser can't produce a genuine GPS fix, callers get a typed GeoError
 * and submission must remain blocked (there is no bypass).
 */
@Injectable({ providedIn: 'root' })
export class GeolocationService {
  getCurrentPosition(): Promise<GeoPosition> {
    if (!navigator.geolocation) {
      return Promise.reject(new GeoError('unsupported', 'Location is not supported in this browser.'));
    }

    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        (position) => resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          timestamp: position.timestamp,
        }),
        (error) => reject(this.mapError(error)),
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
      );
    });
  }

  private mapError(error: GeolocationPositionError): GeoError {
    switch (error.code) {
      case error.PERMISSION_DENIED:
        return new GeoError('permission-denied', 'Location access was denied.');
      case error.POSITION_UNAVAILABLE:
        return new GeoError('unavailable', 'Your location could not be determined.');
      case error.TIMEOUT:
        return new GeoError('timeout', 'Getting your location took too long. Please try again.');
      default:
        return new GeoError('unknown', 'Unable to determine your location.');
    }
  }
}
