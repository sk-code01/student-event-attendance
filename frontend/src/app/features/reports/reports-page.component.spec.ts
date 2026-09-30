import { HttpResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { ReportsPageComponent } from './reports-page.component';
import { ReportType } from '../../core/models/report.model';
import { AuthService } from '../../core/services/auth.service';
import { ReportService } from '../../core/services/report.service';

const STUDENT_TYPES: ReportType[] = [
  { key: 'student-participation', title: 'Student Participation Report', description: 'Your participations.', formats: ['csv', 'xlsx', 'pdf'] },
  { key: 'student-achievement', title: 'Student Achievement Report', description: 'Your achievements.', formats: ['csv', 'xlsx', 'pdf'] },
];

const ADMIN_TYPES: ReportType[] = [
  ...STUDENT_TYPES,
  { key: 'system', title: 'System/Admin Report', description: 'System-wide totals.', formats: ['csv', 'xlsx', 'pdf'] },
];

function stub() {
  const spy = jasmine.createSpyObj<ReportService>(
    'ReportService', ['types', 'preview', 'export', 'filenameFrom'],
  );
  spy.types.and.returnValue(of(STUDENT_TYPES));
  spy.preview.and.returnValue(of({
    key: 'student-participation', title: 'Student Participation Report',
    description: 'Your participations.', columns: ['Student', 'Event'],
    rows: [['studenta', 'CS Event']], row_count: 1, filters: 'no filters',
  }));
  spy.export.and.returnValue(of(new HttpResponse({ body: new Blob(['data']), status: 200 })));
  spy.filenameFrom.and.returnValue('student-participation-20260915.csv');
  return spy;
}

async function configure(service: jasmine.SpyObj<ReportService>, role = 'STUDENT') {
  TestBed.resetTestingModule();
  await TestBed.configureTestingModule({
    imports: [ReportsPageComponent],
    providers: [
      provideRouter([]),
      { provide: ReportService, useValue: service },
      { provide: AuthService, useValue: { currentUser: () => ({ username: 'u', role }) } },
    ],
  }).compileComponents();
}

describe('ReportsPageComponent', () => {
  it('offers only the report types the backend returned', async () => {
    const service = stub();
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.types().length).toBe(2);
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Student Participation Report');
    expect(text).not.toContain('System/Admin Report');
  });

  it('shows an admin the additional types the backend allows', async () => {
    const service = stub();
    service.types.and.returnValue(of(ADMIN_TYPES));
    await configure(service, 'ADMIN');
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('System/Admin Report');
  });

  it('preselects the first available type', async () => {
    const service = stub();
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedType).toBe('student-participation');
  });

  it('shows an empty state when no reports are available', async () => {
    const service = stub();
    service.types.and.returnValue(of([]));
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No reports available');
  });

  it('loads a preview with the chosen filters', async () => {
    const service = stub();
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.dateFrom = '2026-09-01';
    component.loadPreview();
    fixture.detectChanges();

    expect(service.preview).toHaveBeenCalledWith(
      'student-participation', jasmine.objectContaining({ date_from: '2026-09-01' }),
    );
    expect(fixture.nativeElement.textContent).toContain('CS Event');
  });

  it('tells the user an empty report still has headers', async () => {
    const service = stub();
    service.preview.and.returnValue(of({
      key: 'student-participation', title: 'T', description: '',
      columns: ['Student'], rows: [], row_count: 0, filters: 'none',
    }));
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();
    fixture.componentInstance.loadPreview();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('will still contain its column headers');
  });

  it('downloads with the selected format and uses the server filename', async () => {
    const service = stub();
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.format = 'xlsx';
    spyOn(URL, 'createObjectURL').and.returnValue('blob:fake');
    spyOn(URL, 'revokeObjectURL');
    component.download();
    fixture.detectChanges();

    expect(service.export).toHaveBeenCalledWith('student-participation', 'xlsx', jasmine.any(Object));
    expect(component.successMessage()).toContain('student-participation-20260915.csv');
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  it('refuses to generate without a report type', async () => {
    const service = stub();
    service.types.and.returnValue(of([]));
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    fixture.componentInstance.download();
    expect(service.export).not.toHaveBeenCalled();
    expect(fixture.componentInstance.errorMessage()).toContain('Choose a report type');
  });

  it('reports a forbidden report clearly', async () => {
    const service = stub();
    service.export.and.returnValue(throwError(() => ({ status: 403 })));
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    fixture.componentInstance.download();
    expect(fixture.componentInstance.errorMessage()).toContain('not available for your role');
    expect(fixture.componentInstance.downloading()).toBeNull();
  });

  it('reports a validation failure', async () => {
    const service = stub();
    service.preview.and.returnValue(
      throwError(() => ({ status: 400, error: { date_from: ['Expected an ISO date.'] } })),
    );
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    fixture.componentInstance.loadPreview();
    expect(fixture.componentInstance.errorMessage()).toContain('Expected an ISO date.');
  });

  it('reports a generic export failure', async () => {
    const service = stub();
    service.export.and.returnValue(throwError(() => ({ status: 500 })));
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    fixture.componentInstance.download();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to generate');
  });

  it('handles an empty response body without pretending it downloaded', async () => {
    const service = stub();
    // HttpResponse.body is always `T | null`; the component guards against a
    // null body, so the test constructs exactly that case.
    service.export.and.returnValue(
      of(new HttpResponse<Blob>({ body: null, status: 200 })),
    );
    await configure(service);
    const fixture = TestBed.createComponent(ReportsPageComponent);
    fixture.detectChanges();

    fixture.componentInstance.download();
    expect(fixture.componentInstance.errorMessage()).toContain('empty report');
    expect(fixture.componentInstance.successMessage()).toBeNull();
  });
});
