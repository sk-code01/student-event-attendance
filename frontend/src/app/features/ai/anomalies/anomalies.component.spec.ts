import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AnomaliesComponent } from './anomalies.component';
import { AnomaliesResponse } from '../../../core/models/ai.model';
import { Role } from '../../../core/models/user.model';
import { AiService } from '../../../core/services/ai.service';
import { AuthService } from '../../../core/services/auth.service';
import { DISCLAIMER, anomalies, riskSignal, unavailable } from '../ai-fixtures.spec';

describe('AnomaliesComponent', () => {
  let aiService: jasmine.SpyObj<AiService>;
  let role: Role = 'FACULTY';

  beforeEach(async () => {
    aiService = jasmine.createSpyObj('AiService', ['recommendations', 'anomalies', 'engagement']);
    await TestBed.configureTestingModule({
      imports: [AnomaliesComponent],
      providers: [
        provideRouter([]),
        { provide: AiService, useValue: aiService },
        { provide: AuthService, useValue: { currentUser: () => ({ username: 'u', role, department: null }) } },
      ],
    }).compileComponents();
  });

  function render() {
    const fixture = TestBed.createComponent(AnomaliesComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('renders rows in backend order with levels, scores and the signals verbatim', () => {
    role = 'FACULTY';
    aiService.anomalies.and.returnValue(of(anomalies()));
    const el: HTMLElement = render().nativeElement;
    const levels = Array.from(el.querySelectorAll('tbody tr td:first-child .badge')).map((b) => b.textContent?.trim());
    expect(levels).toEqual(['HIGH', 'MEDIUM', 'LOW']);
    expect(el.textContent).toContain('Capture taken 5000 m from the venue (typical: 20 m).');
    expect(el.textContent).toContain('0.612');
    expect(el.textContent).toContain(DISCLAIMER);
  });

  it('shows the summary counts from the backend, not recounted', () => {
    role = 'EVENT_COORDINATOR';
    aiService.anomalies.and.returnValue(of(anomalies({ summary: { HIGH: 9, MEDIUM: 0, LOW: 0 } })));
    const fixture = render();
    expect(fixture.componentInstance.summaryCount(anomalies({ summary: { HIGH: 9, MEDIUM: 0, LOW: 0 } }), 'HIGH')).toBe(9);
    expect(fixture.nativeElement.textContent).toContain('9');
  });

  it('filters the displayed rows client-side without a new request', () => {
    role = 'FACULTY';
    aiService.anomalies.and.returnValue(of(anomalies()));
    const fixture = render();
    fixture.componentInstance.setFilter('HIGH');
    fixture.detectChanges();
    expect(fixture.componentInstance.visibleRows().map((r) => r.evidence_id)).toEqual([7]);
    expect(aiService.anomalies).toHaveBeenCalledTimes(1);
    fixture.componentInstance.setFilter('ALL');
    expect(fixture.componentInstance.visibleRows().length).toBe(3);
  });

  it('offers only a link to the existing review screen — no approve, reject or dismiss control', () => {
    role = 'FACULTY';
    aiService.anomalies.and.returnValue(of(anomalies()));
    const el: HTMLElement = render().nativeElement;
    const buttons = Array.from(el.querySelectorAll('button')).map((b) => b.textContent?.trim() ?? '');
    for (const label of buttons) {
      expect(label).not.toMatch(/approve|reject|dismiss|verify/i);
    }
    const reviewLinks = Array.from(el.querySelectorAll('tbody a')).map((a) => a.getAttribute('href'));
    expect(reviewLinks).toEqual(['/faculty/verification/7', '/faculty/verification/8', '/faculty/verification/9']);
  });

  it('routes an Event Coordinator to the Event Coordinator review screen and gives an Admin no review link', () => {
    role = 'EVENT_COORDINATOR';
    aiService.anomalies.and.returnValue(of(anomalies()));
    let fixture = render();
    expect(fixture.componentInstance.reviewLink(riskSignal())).toEqual(['/event-coordinator/verification', '7']);
    role = 'ADMIN';
    fixture = render();
    expect(fixture.componentInstance.reviewLink(riskSignal())).toBeNull();
  });

  it('says plainly when no feature crossed its threshold instead of inventing a signal', () => {
    role = 'FACULTY';
    aiService.anomalies.and.returnValue(of(anomalies({ results: [riskSignal({ signals: [], risk_level: 'LOW' })] })));
    expect(render().nativeElement.textContent).toContain('No individual feature crossed its stated threshold');
  });

  it('renders the insufficient-data and model-error fallbacks', () => {
    role = 'ADMIN';
    aiService.anomalies.and.returnValue(of(unavailable<AnomaliesResponse>('isolation_forest', 'INSUFFICIENT_DATA')));
    expect(render().nativeElement.textContent).toContain('Not enough data yet');
    aiService.anomalies.and.returnValue(of(unavailable<AnomaliesResponse>('isolation_forest', 'MODEL_ERROR')));
    expect(render().nativeElement.textContent).toContain('could not run just now');
  });

  it('shows the empty scope state', () => {
    role = 'EVENT_COORDINATOR';
    aiService.anomalies.and.returnValue(of(anomalies({ results: [], summary: { HIGH: 0, MEDIUM: 0, LOW: 0 } })));
    expect(render().nativeElement.textContent).toContain('Nothing in your scope');
  });

  it('treats a 403 as a role restriction', () => {
    role = 'FACULTY';
    aiService.anomalies.and.returnValue(throwError(() => ({ status: 403 })));
    expect(render().componentInstance.errorMessage()).toContain('not available for your role');
  });
});
