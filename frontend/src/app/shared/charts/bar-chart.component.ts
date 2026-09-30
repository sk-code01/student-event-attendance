import { Component, computed, input } from '@angular/core';

export interface ChartDatum {
  label: string;
  value: number;
}

/**
 * A horizontal bar chart drawn as inline SVG.
 *
 * No charting library was added: `package.json` had none, and these views need
 * comparative bars and a trend line rather than an interactive plotting
 * toolkit. Inline SVG keeps the bundle unchanged, renders identically in the
 * Karma DOM (so the tests assert on real output), and avoids pulling a
 * dependency in for decoration.
 *
 * Horizontal bars specifically, because the labels here are event titles and
 * department names — long text that would be unreadable rotated under a
 * vertical axis.
 */
@Component({
  selector: 'app-bar-chart',
  standalone: true,
  template: `
    <figure class="mb-0">
      <figcaption class="small fw-semibold mb-2">
        {{ title() }}
        @if (valueLabel()) {
          <span class="text-muted fw-normal">({{ valueLabel() }})</span>
        }
      </figcaption>

      @if (data().length === 0) {
        <p class="text-muted small mb-0">{{ emptyMessage() }}</p>
      } @else {
        <svg
          [attr.viewBox]="'0 0 100 ' + height()"
          preserveAspectRatio="none"
          class="w-100"
          [style.height.px]="height() * 3"
          role="img"
          [attr.aria-label]="title()"
        >
          @for (row of rows(); track row.label) {
            <g>
              <rect
                x="0"
                [attr.y]="row.y"
                [attr.width]="row.width"
                [attr.height]="barHeight"
                class="bar"
                rx="0.6"
              ></rect>
            </g>
          }
        </svg>

        <!-- The readable layer. SVG scales the bars; the numbers live in real
             DOM text so they stay legible and screen-reader friendly. -->
        <ul class="list-unstyled small mb-0 mt-2">
          @for (row of rows(); track row.label) {
            <li class="d-flex justify-content-between gap-2 border-bottom py-1">
              <span class="text-truncate" [title]="row.label">{{ row.label }}</span>
              <span class="fw-semibold flex-shrink-0">{{ row.value }}</span>
            </li>
          }
        </ul>
      }
    </figure>
  `,
  styles: [`
    .bar { fill: var(--bs-primary, #0d6efd); }
    svg { overflow: visible; }
  `],
})
export class BarChartComponent {
  readonly title = input('');
  readonly valueLabel = input('');
  readonly data = input<ChartDatum[]>([]);
  readonly emptyMessage = input('No data for this selection.');
  /** Bars beyond this are dropped — a chart with 200 rows is a table. */
  readonly maxBars = input(10);

  protected readonly barHeight = 6;
  private readonly gap = 3;

  protected readonly rows = computed(() => {
    const visible = this.data().slice(0, this.maxBars());
    // Guard the divisor: an all-zero dataset must render flat bars, not NaN.
    const max = Math.max(...visible.map((d) => d.value), 0);
    return visible.map((datum, index) => ({
      label: datum.label || '(none)',
      value: datum.value,
      y: index * (this.barHeight + this.gap),
      width: max > 0 ? Math.max((datum.value / max) * 100, datum.value > 0 ? 1 : 0) : 0,
    }));
  });

  protected readonly height = computed(() => {
    const count = Math.min(this.data().length, this.maxBars());
    return Math.max(count * (this.barHeight + this.gap), this.barHeight);
  });
}
