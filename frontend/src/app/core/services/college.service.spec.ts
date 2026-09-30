import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { CollegeService } from './college.service';

describe('CollegeService', () => {
  let service: CollegeService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(CollegeService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists colleges with the default page size', () => {
    service.list().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/colleges/`);
    expect(req.request.method).toBe('GET');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('asks for every college in one page when the caller needs a dropdown', () => {
    // The API caps page_size at 200. Without this, a dropdown would silently
    // show only the first 20 colleges and give no sign that others exist.
    service.list({ all: true }).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/colleges/?page_size=200`);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('page_size')).toBe('200');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('creates a college', () => {
    service.create({ name: 'Engineering College', code: 'ENGG' }).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/colleges/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'Engineering College', code: 'ENGG' });
    req.flush({});
  });
});
