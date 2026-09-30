import { Component, computed, input } from '@angular/core';

export interface LineSeries {
  name: string;
  colour: string;
  values: number[];
}

/**
 * A multi-series line chart for time trends, drawn as inline SVG.
 *
 * Handles the awkward shapes explicitly rather than assuming a well-formed
 * series: zero periods renders an empty-state message, a single period lists
 * the values instead of drawing a plot (one point is not a trend, and an
 * almost-empty chart reads as a broken one), and an all-zero series renders a
 * flat baseline instead of dividing by zero.
 */
@Component({
  selector: 'app-line-chart',
  standalone: true,
  template: `
    <figure class="mb-0">
      <figcaption class="small fw-semibold mb-2">{{ title() }}</figcaption>

      @if (labels().length === 0) {
        <p class="text-muted small mb-0">{{ emptyMessage() }}</p>
      } @else if (labels().length === 1) {
        <!-- One time bucket is not a trend. Drawing 200px of empty plot with a
             single mark in it looks like a broken chart, so the values are
             stated plainly instead and the shape is left until there is one. -->
        <p class="text-muted small mb-2">
          Only one period ({{ labels()[0] }}) falls in this range — not enough to draw a trend.
        </p>
        <ul class="meta-list">
          @for (line of lines(); track line.name) {
            <li class="meta-row">
              <span class="meta-key">
                <span class="legend-swatch" [style.background]="line.colour"></span>
                {{ line.name }}
              </span>
              <span class="meta-val">{{ line.values[0] }}</span>
            </li>
          }
        </ul>
      } @else {
        <svg viewBox="0 0 100 40" preserveAspectRatio="none" class="w-100"
             style="height: 200px" role="img" [attr.aria-label]="title()">
          <!-- baseline + midline for scale -->
          <line x1="0" y1="38" x2="100" y2="38" class="axis"></line>
          <line x1="0" y1="20" x2="100" y2="20" class="gridline"></line>

          @for (line of lines(); track line.name) {
            <polyline
              [attr.points]="line.path"
              fill="none"
              [attr.stroke]="line.colour"
              stroke-width="0.8"
              vector-effect="non-scaling-stroke"
            ></polyline>
          }
        </svg>

        <div class="d-flex flex-wrap gap-3 small mt-2">
          @for (line of lines(); track line.name) {
            <span class="d-inline-flex align-items-center gap-1">
              <span class="legend-swatch" [style.background]="line.colour"></span>
              {{ line.name }}
            </span>
          }
        </div>

        <div class="d-flex justify-content-between small text-muted mt-1">
          <span>{{ labels()[0] }}</span>
          @if (labels().length > 1) {
            <span>{{ labels()[labels().length - 1] }}</span>
          }
        </div>
        <div class="small text-muted">Peak value: {{ maxValue() }}</div>
      }
    </figure>
  `,
  styles: [`
    /* Themed, not fixed greys: these lines have to stay legible on the dark
       surfaces as well as the light ones. */
    .axis { stroke: var(--border-strong, #adb5bd); stroke-width: 0.3; vector-effect: non-scaling-stroke; }
    .gridline { stroke: var(--border-subtle, #dee2e6); stroke-width: 0.2; stroke-dasharray: 1 1; vector-effect: non-scaling-stroke; }
    .legend-swatch { width: 0.75rem; height: 0.75rem; border-radius: 0.125rem; display: inline-block; }
    svg { overflow: visible; }
  `],
})
export class LineChartComponent {
  readonly title = input('');
  readonly labels = input<string[]>([]);
  readonly series = input<LineSeries[]>([]);
  readonly emptyMessage = input('No data for this period.');

  protected readonly maxValue = computed(() =>
    Math.max(...this.series().flatMap((s) => s.values), 0),
  );

  protected readonly lines = computed(() => {
    const labels = this.labels();
    const max = this.maxValue();
    const span = labels.length > 1 ? labels.length - 1 : 1;

    return this.series().map((s) => {
      const points = labels.map((_, index) => ({
        x: (index / span) * 100,
        // Top margin of 2, baseline at 38. An all-zero series sits flat on
        // the baseline rather than producing NaN.
        y: max > 0 ? 38 - (s.values[index] ?? 0) / max * 36 : 38,
      }));
      return {
        name: s.name,
        colour: s.colour,
        values: s.values,
        points,
        path: points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' '),
      };
    });
  });
}
