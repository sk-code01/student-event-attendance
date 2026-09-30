import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { BarChartComponent, ChartDatum } from './bar-chart.component';
import { LineChartComponent, LineSeries } from './line-chart.component';

@Component({
  standalone: true,
  imports: [BarChartComponent],
  template: `<app-bar-chart [title]="title" [data]="data" [maxBars]="maxBars" />`,
})
class BarHost {
  title = 'Participations by event';
  data: ChartDatum[] = [];
  maxBars = 10;
}

@Component({
  standalone: true,
  imports: [LineChartComponent],
  template: `<app-line-chart [title]="title" [labels]="labels" [series]="series" />`,
})
class LineHost {
  title = 'Activity over time';
  labels: string[] = [];
  series: LineSeries[] = [];
}

describe('BarChartComponent', () => {
  async function render(setup: (host: BarHost) => void) {
    await TestBed.configureTestingModule({ imports: [BarHost] }).compileComponents();
    const fixture = TestBed.createComponent(BarHost);
    setup(fixture.componentInstance);
    fixture.detectChanges();
    return fixture;
  }

  it('shows an empty-state message and no svg when there is no data', async () => {
    const fixture = await render((h) => (h.data = []));
    expect(fixture.nativeElement.textContent).toContain('No data for this selection.');
    expect(fixture.nativeElement.querySelector('svg')).toBeNull();
  });

  it('renders one bar and one readable row per datum', async () => {
    const fixture = await render((h) => (h.data = [
      { label: 'CS Event', value: 5 },
      { label: 'EC Event', value: 3 },
    ]));
    expect(fixture.nativeElement.querySelectorAll('rect').length).toBe(2);
    expect(fixture.nativeElement.querySelectorAll('li').length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('CS Event');
    expect(fixture.nativeElement.textContent).toContain('5');
  });

  it('does not divide by zero when every value is zero', async () => {
    const fixture = await render((h) => (h.data = [
      { label: 'A', value: 0 },
      { label: 'B', value: 0 },
    ]));
    const widths = Array.from(fixture.nativeElement.querySelectorAll('rect'))
      .map((r) => (r as SVGRectElement).getAttribute('width'));
    expect(widths.every((w) => w === '0')).toBeTrue();
    expect(fixture.nativeElement.textContent).not.toContain('NaN');
  });

  it('handles a single data point', async () => {
    const fixture = await render((h) => (h.data = [{ label: 'Only', value: 9 }]));
    expect(fixture.nativeElement.querySelectorAll('rect').length).toBe(1);
  });

  it('caps the number of bars', async () => {
    const fixture = await render((h) => {
      h.maxBars = 3;
      h.data = Array.from({ length: 20 }, (_, i) => ({ label: `E${i}`, value: i + 1 }));
    });
    expect(fixture.nativeElement.querySelectorAll('rect').length).toBe(3);
  });

  it('labels a blank category rather than rendering nothing', async () => {
    const fixture = await render((h) => (h.data = [{ label: '', value: 2 }]));
    expect(fixture.nativeElement.textContent).toContain('(none)');
  });

  it('keeps large values readable', async () => {
    const fixture = await render((h) => (h.data = [
      { label: 'Big', value: 1000000 }, { label: 'Small', value: 1 },
    ]));
    expect(fixture.nativeElement.textContent).toContain('1000000');
    expect(fixture.nativeElement.querySelectorAll('rect').length).toBe(2);
  });
});

describe('LineChartComponent', () => {
  async function render(setup: (host: LineHost) => void) {
    await TestBed.configureTestingModule({ imports: [LineHost] }).compileComponents();
    const fixture = TestBed.createComponent(LineHost);
    setup(fixture.componentInstance);
    fixture.detectChanges();
    return fixture;
  }

  it('shows an empty-state message with no labels', async () => {
    const fixture = await render((h) => (h.labels = []));
    expect(fixture.nativeElement.textContent).toContain('No data for this period.');
    expect(fixture.nativeElement.querySelector('svg')).toBeNull();
  });

  it('renders a polyline per series with a legend', async () => {
    const fixture = await render((h) => {
      h.labels = ['2026-08', '2026-09'];
      h.series = [
        { name: 'Registrations', colour: '#0d6efd', values: [1, 3] },
        { name: 'Participations', colour: '#198754', values: [0, 2] },
      ];
    });
    expect(fixture.nativeElement.querySelectorAll('polyline').length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('Registrations');
    expect(fixture.nativeElement.textContent).toContain('2026-08');
    expect(fixture.nativeElement.textContent).toContain('Peak value: 3');
  });

  it('states the values instead of plotting when there is only one period', async () => {
    const fixture = await render((h) => {
      h.labels = ['2026-09'];
      h.series = [{ name: 'Registrations', colour: '#0d6efd', values: [4] }];
    });
    // One point is not a trend: a 200px plot holding a single mark reads as a
    // broken chart, so the value is stated and the shape is left until there
    // is one to show.
    expect(fixture.nativeElement.querySelector('svg')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('not enough to draw a trend');
    expect(fixture.nativeElement.textContent).toContain('Registrations');
    expect(fixture.nativeElement.textContent).toContain('4');
  });

  it('draws a flat baseline for an all-zero series instead of NaN coordinates', async () => {
    const fixture = await render((h) => {
      h.labels = ['2026-08', '2026-09'];
      h.series = [{ name: 'Registrations', colour: '#0d6efd', values: [0, 0] }];
    });
    const points = fixture.nativeElement.querySelector('polyline').getAttribute('points');
    expect(points).not.toContain('NaN');
    expect(points).toContain('38.00');
  });

  it('tolerates a series shorter than the label list', async () => {
    const fixture = await render((h) => {
      h.labels = ['a', 'b', 'c'];
      h.series = [{ name: 'Short', colour: '#000', values: [1] }];
    });
    const points = fixture.nativeElement.querySelector('polyline').getAttribute('points');
    expect(points).not.toContain('NaN');
  });
});
