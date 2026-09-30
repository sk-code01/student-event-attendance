import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { DashboardAiPanelComponent } from './dashboard-ai-panel.component';
import { EngagementResponse, RecommendationsResponse } from '../../../core/models/ai.model';
import { Role } from '../../../core/models/user.model';
import { AiService } from '../../../core/services/ai.service';
import { AuthService } from '../../../core/services/auth.service';
import { anomalies, coldStart, engagementStaff, engagementStudent, recommendations, unavailable } from '../ai-fixtures.spec';

describe('DashboardAiPanelComponent', () => {
  let aiService: jasmine.SpyObj<AiService>;
  let role: Role = 'STUDENT';

  beforeEach(async () => {
    aiService = jasmine.createSpyObj('AiService', ['recommendations', 'anomalies', 'engagement']);
    aiService.recommendations.and.returnValue(of(recommendations()));
    aiService.anomalies.and.returnValue(of(anomalies()));
    aiService.engagement.and.returnValue(of(engagementStaff()));
    await TestBed.configureTestingModule({
      imports: [DashboardAiPanelComponent],
      providers: [
        provideRouter([]),
        { provide: AiService, useValue: aiService },
        { provide: AuthService, useValue: { currentUser: () => ({ username: 'u', role, department: null }) } },
      ],
    }).compileComponents();
  });

  function render() {
    const fixture = TestBed.createComponent(DashboardAiPanelComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('requests recommendations and engagement for a student, never the staff risk view', () => {
    role = 'STUDENT';
    aiService.engagement.and.returnValue(of(engagementStudent()));
    const text: string = render().nativeElement.textContent;
    expect(aiService.recommendations).toHaveBeenCalledWith(3);
    expect(aiService.engagement).toHaveBeenCalledTimes(1);
    expect(aiService.anomalies).not.toHaveBeenCalled();
    expect(text).toContain('Recommended for you');
    expect(text).toContain('CS Tech Open');
    expect(text).toContain('MODERATE');
    expect(text).not.toContain('Evidence risk signals');
  });

  it('requests engagement and risk signals for staff, never recommendations', () => {
    role = 'EVENT_COORDINATOR';
    const text: string = render().nativeElement.textContent;
    expect(aiService.recommendations).not.toHaveBeenCalled();
    expect(aiService.anomalies).toHaveBeenCalledWith({ limit: 5 });
    expect(text).toContain('Evidence risk signals');
    expect(text).toContain('4 students in your scope');
    expect(text).not.toContain('Recommended for you');
  });

  it('marks cold-start picks as starter picks', () => {
    role = 'STUDENT';
    aiService.recommendations.and.returnValue(of(coldStart()));
    aiService.engagement.and.returnValue(of(engagementStudent()));
    expect(render().nativeElement.textContent).toContain('Starter picks');
  });

  it('degrades each card independently when a model is unavailable or errors', () => {
    role = 'STUDENT';
    aiService.recommendations.and.returnValue(of(unavailable<RecommendationsResponse>('knn', 'MODEL_ERROR')));
    aiService.engagement.and.returnValue(throwError(() => ({ status: 500 })));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('could not run just now');
    expect(text).toContain('Engagement clusters could not be loaded');
    expect(text).toContain('Decision support only');
  });

  it('shows insufficient data as a message, not as zeros', () => {
    role = 'ADMIN';
    aiService.engagement.and.returnValue(of(unavailable<EngagementResponse>('kmeans', 'INSUFFICIENT_DATA')));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('Not enough data yet');
    expect(text).not.toContain('NaN');
  });
});
