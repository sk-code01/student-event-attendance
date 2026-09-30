import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AchievementService } from './achievement.service';

describe('AchievementService', () => {
  let service: AchievementService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(AchievementService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('creates an achievement without ever sending a status', () => {
    service
      .create({
        participation: 9,
        title: 'First Place',
        achievement_type: 'Competition',
        achievement_date: '2026-09-14',
      })
      .subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/achievements/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body.status).toBeUndefined();
    expect(req.request.body.participation).toBe(9);
    req.flush({ id: 1, status: 'PENDING_APPROVAL' });
  });

  it('patches a draft', () => {
    service.update(4, { title: 'Runner Up' }).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/achievements/4/`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ title: 'Runner Up' });
    req.flush({ id: 4, title: 'Runner Up' });
  });

  it('submits, approves and rejects through dedicated actions', () => {
    service.submit(4).subscribe();
    let req = httpMock.expectOne(`${environment.apiBaseUrl}/achievements/4/submit/`);
    req.flush({ id: 4, status: 'PENDING_APPROVAL' });

    service.approve(4).subscribe();
    req = httpMock.expectOne(`${environment.apiBaseUrl}/achievements/4/approve/`);
    expect(req.request.body).toEqual({});
    req.flush({ id: 4, status: 'APPROVED' });

    service.reject(4, 'not official').subscribe();
    req = httpMock.expectOne(`${environment.apiBaseUrl}/achievements/4/reject/`);
    expect(req.request.body).toEqual({ reason: 'not official' });
    req.flush({ id: 4, status: 'REJECTED' });
  });
});
