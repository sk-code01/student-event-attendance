import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { RecommendationsComponent } from './recommendations.component';
import { RecommendationsResponse } from '../../../core/models/ai.model';
import { AiService } from '../../../core/services/ai.service';
import { DISCLAIMER, coldStart, recommendations, unavailable } from '../ai-fixtures.spec';

describe('RecommendationsComponent', () => {
  let aiService: jasmine.SpyObj<AiService>;

  beforeEach(async () => {
    aiService = jasmine.createSpyObj('AiService', ['recommendations', 'anomalies', 'engagement']);
    await TestBed.configureTestingModule({
      imports: [RecommendationsComponent],
      providers: [provideRouter([]), { provide: AiService, useValue: aiService }],
    }).compileComponents();
  });

  function render() {
    const fixture = TestBed.createComponent(RecommendationsComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('renders the ranked list with the backend reasons verbatim and the disclaimer', () => {
    aiService.recommendations.and.returnValue(of(recommendations()));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('1. CS Tech Open');
    expect(text).toContain('2. CS Sports Open');
    expect(text).toContain('Matches a category you have engaged with before (Technical).');
    expect(text).toContain(DISCLAIMER);
    expect(text).toContain('Not a probability');
    expect(text).toContain('similarity');
  });

  it('keeps the backend order and never re-ranks', () => {
    aiService.recommendations.and.returnValue(of(recommendations()));
    const fixture = render();
    const titles = Array.from(fixture.nativeElement.querySelectorAll('.rec-title'))
      .map((el) => (el as HTMLElement).textContent?.trim());
    expect(titles).toEqual(['1. CS Tech Open', '2. CS Sports Open']);
    expect(fixture.componentInstance.response()?.results[0].event_id).toBe(11);
  });

  it('labels the cold-start case honestly', () => {
    aiService.recommendations.and.returnValue(of(coldStart()));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('Getting started');
    expect(text).toContain('no participation history yet');
    expect(text).toContain('rank score');
    expect(text).not.toContain('similarity');
  });

  it('shows a calm empty state when nothing is actionable', () => {
    aiService.recommendations.and.returnValue(of(recommendations({
      results: [], reason: 'NO_ACTIONABLE_EVENTS',
      detail: 'There are no events currently open for registration that you have not already registered for.',
    })));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('no events currently open for registration');
    expect(text).not.toContain('unavailable');
  });

  it('renders the controlled fallback when the model failed', () => {
    aiService.recommendations.and.returnValue(of(unavailable<RecommendationsResponse>('knn', 'MODEL_ERROR')));
    const text: string = render().nativeElement.textContent;
    expect(text).toContain('Recommendations unavailable');
    expect(text).toContain('Nothing else in the system is affected');
    expect(text).toContain(DISCLAIMER);
  });

  it('explains a 403 as a role restriction rather than a crash', () => {
    aiService.recommendations.and.returnValue(throwError(() => ({ status: 403 })));
    const fixture = render();
    expect(fixture.componentInstance.errorMessage()).toContain('not available for your role');
    expect(fixture.nativeElement.textContent).toContain(DISCLAIMER);
  });

  it('offers no register/approve control — only a link to the ordinary event page', () => {
    aiService.recommendations.and.returnValue(of(recommendations()));
    const el: HTMLElement = render().nativeElement;
    expect(el.querySelectorAll('button').length).toBe(1); // Refresh
    const links = Array.from(el.querySelectorAll('a.list-group-item')).map((a) => a.getAttribute('href'));
    expect(links).toEqual(['/student/events/11', '/student/events/12']);
  });
});
