import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { AuthService } from './auth.service';
import { EvidenceService } from './evidence.service';
import { ParticipationService } from './participation.service';
import { PendingEvidenceCapture, CaptureRole } from '../models/evidence.model';

const DB_NAME = 'ssepams-offline-captures';
const DB_VERSION = 1;
const STORE_NAME = 'queue';

interface QueuedCapture {
  role: CaptureRole;
  blob: Blob;
  deviceCaptureTimestamp: string;
  latitude: number;
  longitude: number;
  gpsAccuracy: number;
}

export interface QueuedSession {
  id: string;
  userId: number;
  eventId: number;
  eventTitle: string;
  /** Set only for a resubmission queued offline — an existing participation
   * that already has evidence, vs. a first-time submission which still
   * needs to open a Participation for `eventId` at sync time. */
  participationId: number | null;
  captures: QueuedCapture[];
  status: 'PENDING' | 'SYNCING' | 'FAILED';
  lastError: string | null;
  createdAt: string;
}

/**
 * "Capture now, upload later." Queued sessions are stored in IndexedDB
 * (never localStorage — image Blobs don't belong there) and are bound to
 * the authenticated user's id, so if a different student logs into the
 * same browser they never see or can trigger a retry of someone else's
 * queued capture. No JWT/token is ever stored in a queued record — sync
 * requests go through the normal authenticated HttpClient (and its
 * existing refresh-on-401 interceptor), using whatever session is active
 * at sync time.
 *
 * Known limitation (documented rather than silently ignored): IndexedDB
 * here is NOT encrypted. If this device is shared or compromised, a queued
 * capture's image and coordinates could be read from browser storage
 * before it uploads. Full client-side encryption is out of scope for this
 * phase.
 */
@Injectable({ providedIn: 'root' })
export class OfflineCaptureQueueService {
  private dbPromise: Promise<IDBDatabase> | null = null;

  readonly pendingCount = signal(0);

  constructor(
    private readonly participationService: ParticipationService,
    private readonly evidenceService: EvidenceService,
    private readonly authService: AuthService,
  ) {
    window.addEventListener('online', () => this.syncAll());
    this.refreshPendingCount();
    if (navigator.onLine) {
      this.syncAll();
    }
  }

  async enqueue(params: {
    eventId: number;
    eventTitle: string;
    captures: PendingEvidenceCapture[];
    participationId?: number;
  }): Promise<void> {
    const userId = this.authService.currentUser()?.id;
    if (!userId) {
      throw new Error('Cannot queue a capture without an authenticated user.');
    }

    const record: QueuedSession = {
      id: crypto.randomUUID(),
      userId,
      eventId: params.eventId,
      eventTitle: params.eventTitle,
      participationId: params.participationId ?? null,
      captures: params.captures.map((c) => ({
        role: c.role,
        blob: c.blob,
        deviceCaptureTimestamp: c.deviceCaptureTimestamp,
        latitude: c.latitude,
        longitude: c.longitude,
        gpsAccuracy: c.gpsAccuracy,
      })),
      status: 'PENDING',
      lastError: null,
      createdAt: new Date().toISOString(),
    };

    const db = await this.openDb();
    await this.runTransaction(db, 'readwrite', (store) => store.put(record));
    await this.refreshPendingCount();
  }

  async listForCurrentUser(): Promise<QueuedSession[]> {
    const userId = this.authService.currentUser()?.id;
    if (!userId) return [];
    const all = await this.listAll();
    return all.filter((session) => session.userId === userId);
  }

  async discard(id: string): Promise<void> {
    const db = await this.openDb();
    await this.runTransaction(db, 'readwrite', (store) => store.delete(id));
    await this.refreshPendingCount();
  }

  /** Called automatically when the browser regains connectivity, and once
   * eagerly at startup in case captures were queued in a previous offline
   * session. Also safe to call manually from a "Retry now" UI action. */
  async syncAll(): Promise<void> {
    if (!navigator.onLine) return;
    const sessions = await this.listForCurrentUser();
    for (const session of sessions) {
      if (session.status === 'SYNCING') continue;
      await this.syncOne(session);
    }
    await this.refreshPendingCount();
  }

  private async syncOne(session: QueuedSession): Promise<void> {
    await this.updateStatus(session.id, 'SYNCING', null);
    try {
      const pendingCaptures: PendingEvidenceCapture[] = session.captures.map((c) => ({
        role: c.role,
        blob: c.blob,
        previewUrl: '',
        deviceCaptureTimestamp: c.deviceCaptureTimestamp,
        latitude: c.latitude,
        longitude: c.longitude,
        gpsAccuracy: c.gpsAccuracy,
      }));
      const participationId = session.participationId
        ?? (await firstValueFrom(this.participationService.open(session.eventId))).id;
      await this.evidenceService.submitCaptureSession(participationId, pendingCaptures);
      await this.discard(session.id);
    } catch (error: unknown) {
      // Permanent (4xx) validation/authorization failures must not retry
      // forever — they're marked FAILED so the UI can show the student why
      // and let them discard it. Network/5xx failures stay PENDING and
      // will be retried on the next 'online' event or manual retry.
      const httpError = error as { status?: number; error?: { detail?: string } };
      const isPermanent = typeof httpError?.status === 'number' && httpError.status >= 400 && httpError.status < 500;
      await this.updateStatus(session.id, isPermanent ? 'FAILED' : 'PENDING', this.describeError(httpError));
    }
  }

  private describeError(error: { status?: number; error?: { detail?: string } }): string {
    if (!error || error.status === 0 || error.status === undefined) return 'No network connection.';
    if (error.status === 400) return error.error?.detail || 'This capture could not be validated.';
    if (error.status === 401 || error.status === 403) return 'Your session expired. Log in again to retry.';
    if (error.status === 409) return 'This participation was already submitted.';
    if (error.status === 413) return 'The image was too large.';
    if (error.status >= 500) return 'The server is temporarily unavailable. Will retry automatically.';
    return 'Upload failed. Will retry automatically.';
  }

  private async refreshPendingCount(): Promise<void> {
    const sessions = await this.listForCurrentUser();
    this.pendingCount.set(sessions.length);
  }

  private async updateStatus(id: string, status: QueuedSession['status'], lastError: string | null): Promise<void> {
    const db = await this.openDb();
    await this.runTransaction(db, 'readwrite', (store) => {
      const getRequest = store.get(id);
      getRequest.onsuccess = () => {
        const record = getRequest.result as QueuedSession | undefined;
        if (record) {
          record.status = status;
          record.lastError = lastError;
          store.put(record);
        }
      };
      return getRequest;
    });
  }

  private async listAll(): Promise<QueuedSession[]> {
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const request = tx.objectStore(STORE_NAME).getAll();
      request.onsuccess = () => resolve(request.result as QueuedSession[]);
      request.onerror = () => reject(request.error);
    });
  }

  private openDb(): Promise<IDBDatabase> {
    if (!this.dbPromise) {
      this.dbPromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: 'id' });
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    }
    return this.dbPromise;
  }

  private runTransaction(
    db: IDBDatabase,
    mode: IDBTransactionMode,
    action: (store: IDBObjectStore) => unknown,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      action(tx.objectStore(STORE_NAME));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
}
