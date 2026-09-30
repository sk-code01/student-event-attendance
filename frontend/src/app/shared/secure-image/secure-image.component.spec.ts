import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { SecureImageComponent } from './secure-image.component';

describe('SecureImageComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SecureImageComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('fetches the image as a blob via HttpClient (so the auth interceptor attaches the token) and renders an object URL', () => {
    const fixture = TestBed.createComponent(SecureImageComponent);
    fixture.componentInstance.src = '/api/v1/evidence/captures/1/image/';
    fixture.componentInstance.ngOnChanges();
    fixture.detectChanges();

    const req = httpMock.expectOne('/api/v1/evidence/captures/1/image/');
    expect(req.request.responseType).toBe('blob');
    req.flush(new Blob(['x'], { type: 'image/jpeg' }));
    fixture.detectChanges();

    expect(fixture.componentInstance.objectUrl()).toContain('blob:');
    const img: HTMLImageElement = fixture.nativeElement.querySelector('img');
    expect(img.src).toContain('blob:');
  });

  it('shows an "Image unavailable" message when the fetch fails', () => {
    const fixture = TestBed.createComponent(SecureImageComponent);
    fixture.componentInstance.src = '/api/v1/evidence/captures/1/image/';
    fixture.componentInstance.ngOnChanges();
    fixture.detectChanges();

    const req = httpMock.expectOne('/api/v1/evidence/captures/1/image/');
    req.flush(new Blob(['forbidden']), { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();

    expect(fixture.componentInstance.failed()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Image unavailable');
  });
});
