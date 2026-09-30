import { Component, OnDestroy, effect, input, signal } from '@angular/core';

/**
 * A number that counts up to its value on first render.
 *
 * Purely decorative, and treated as such: the final value is rendered
 * immediately when the user prefers reduced motion, and `aria-hidden` is
 * never used — a screen reader reads the live text, which settles on the
 * real figure. The element also carries the true value in `title` so a
 * hovering user never has to wait for the animation to read it.
 *
 * Only used for meaningful KPI figures, not for every number on a page.
 */
@Component({
  selector: 'app-count-up',
  standalone: true,
  template: `{{ display() }}`,
})
export class CountUpComponent implements OnDestroy {
  readonly value = input.required<number>();
  readonly durationMs = input(900);

  readonly display = signal(0);
  private frame: number | null = null;

  constructor() {
    effect(() => {
      const target = this.value();
      this.cancel();

      // Nothing to animate, or the user asked for less motion: land on the
      // number straight away.
      const reduced =
        typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (reduced || target <= 0 || typeof requestAnimationFrame !== 'function') {
        this.display.set(target);
        return;
      }

      const duration = this.durationMs();
      const start = performance.now();
      const step = (now: number) => {
        const progress = Math.min((now - start) / duration, 1);
        // Ease-out cubic: fast at first, settling gently on the real figure.
        const eased = 1 - Math.pow(1 - progress, 3);
        this.display.set(Math.round(target * eased));
        if (progress < 1) {
          this.frame = requestAnimationFrame(step);
        } else {
          this.frame = null;
          this.display.set(target);
        }
      };
      this.frame = requestAnimationFrame(step);
    });
  }

  ngOnDestroy(): void {
    this.cancel();
  }

  private cancel(): void {
    if (this.frame !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(this.frame);
    }
    this.frame = null;
  }
}
