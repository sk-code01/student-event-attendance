import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { EngagementComponent } from './engagement.component';
import { EngagementResponse } from '../../../core/models/ai.model';
import { Role } from '../../../core/models/user.model';
import { AiService } from '../../../core/services/ai.service';
import { AuthService } from '../../../core/services/auth.service';
import { DISCLAIMER, engagementStaff, engagementStudent, unavailable } from '../ai-fixtures.spec';

describe('EngagementComponent', () => {
  let aiService: jasmine.SpyObj<AiService>;
  let role: Role = 'EVENT_COORDINATOR';

  beforeEach(async () => {
    aiService = jasmine.createSpyObj('AiService', ['recommendations', 'anomalies', 'engagement']);
    await TestBed.configureTestingModule({
      imports: [EngagementComponent],
      providers: [
        provideRouter([]),
        { provide: AiService, useValue: aiService },
        { provide: AuthService, useValue: { currentUser: () => ({ username: 'u', role, department: null }) } },
      ],
    }).compileComponents();
  });

  function render() {
    const fixture = TestBed.createComponent(EngagementComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('renders the distribution in the backend label order, never by cluster id', () => {
    role = 'EVENT_COORDINATOR';
    aiService.engagement.and.returnValue(of(engagementStaff()));
    const fixture = render();
    const rows = fixture.componentInstance.distributionRows(engagementStaff());
    expect(rows.map((r) => r.label)).toEqual(['LOW', 'MODERATE', 'HIGH']);
    expect(rows.map((r) => r.count)).toEqual([2, 1, 1]);
    expect(rows.map((r) => r.percent)).toEqual([50, 25, 25]);
    expect(fixture.nativeElement.textContent).toContain('4 students in your scope');
  });

  it('shows per-student rows for Event Coordinator/Admin', () => {
    role = 'EVENT_COORDINATOR';
    aiService.engagement.and.returnValue(of(engagementStaff()));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('studentcold');
    expect(text).toContain('studenthigh');
    expect(text).toContain(DISCLAIMER);
  });

  it('shows the distribution only when the backend sent no identities (Faculty)', () => {
    role = 'FACULTY';
    aiService.engagement.and.returnValue(of(engagementStaff({ results: [] })));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('Distribution');
    expect(text).not.toContain('studentcold');
    expect(text).toContain('shown to Event Coordinator and Admin accounts only');
  });

  it('shows a student only their own label and explanation', () => {
    role = 'STUDENT';
    aiService.engagement.and.returnValue(of(engagementStudent()));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('Your engagement cluster');
    expect(text).toContain('MODERATE');
    expect(text).toContain('not an academic judgment');
    expect(text).not.toContain('Distribution');
    expect(text).not.toContain('studenthigh');
  });

  it('renders a zero-percent distribution without NaN', () => {
    role = 'EVENT_COORDINATOR';
    aiService.engagement.and.returnValue(of(engagementStaff({ distribution: { LOW: 0, MODERATE: 0, HIGH: 0 }, scoped_students: 0, results: [] })));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('No students in your scope');
    expect(text).not.toContain('NaN');
  });

  it('renders the insufficient-data fallback', () => {
    role = 'ADMIN';
    aiService.engagement.and.returnValue(of(unavailable<EngagementResponse>('kmeans', 'INSUFFICIENT_DATA')));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('Engagement clusters unavailable');
    expect(text).toContain('Not enough data yet');
  });

  it('renders the note when all students were identical', () => {
    role = 'ADMIN';
    aiService.engagement.and.returnValue(of(engagementStaff({
      k: 1, label_order: ['MODERATE'], distribution: { MODERATE: 4 },
      note: 'All students have identical feature vectors; one MODERATE group.',
    })));
    expect(render().nativeElement.textContent).toContain('identical feature vectors');
  });

  it('shows a network error without hiding the disclaimer', () => {
    role = 'ADMIN';
    aiService.engagement.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = render();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
    expect(fixture.nativeElement.textContent).toContain('Decision support only');
  });
});
