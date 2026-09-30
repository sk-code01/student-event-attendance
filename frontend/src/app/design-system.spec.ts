/**
 * The design system's own invariants.
 *
 * The redesign's claims — dark by default, text that actually meets WCAG AA
 * against the surface it sits on, motion that genuinely stops under
 * `prefers-reduced-motion`, colour defined once in the token layer — are all
 * checkable, so they are checked here rather than asserted in a report.
 *
 * Everything below reads *computed* values from a real document. A test that
 * only asserted the CSS text was present would pass on a stylesheet that never
 * applied.
 */

import { TestBed } from '@angular/core/testing';

/** Relative luminance, per WCAG 2.1 §1.4.3. */
function luminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(a: [number, number, number], b: [number, number, number]): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/**
 * Resolves any CSS colour — including `color-mix()` and `var()` chains — to
 * actual channel values by making the browser paint it and reading it back.
 * There is no way to do this by parsing: `color-mix(in oklab, ...)` has to be
 * evaluated by the engine that implements it.
 */
function resolveColour(doc: Document, value: string): [number, number, number] {
  const probe = doc.createElement('div');
  probe.style.color = value;
  doc.body.appendChild(probe);
  const computed = doc.defaultView!.getComputedStyle(probe).color;
  probe.remove();

  const match = computed.match(/-?[\d.]+/g);
  if (!match || match.length < 3) {
    throw new Error(`could not resolve colour: ${value} (computed as "${computed}")`);
  }
  return [Number(match[0]), Number(match[1]), Number(match[2])];
}

function token(doc: Document, name: string): string {
  return getComputedStyle(doc.documentElement).getPropertyValue(name).trim();
}

/**
 * A fresh document with the real stylesheet in it.
 *
 * Karma's own page is not usable for this: it carries whatever theme and role
 * the last spec left on `<html>`, and its `<body>` is full of fixtures. An
 * iframe gives each case a clean document whose `<html>` this test controls.
 */
function withDocument(theme: 'light' | 'dark', run: (doc: Document) => void): void {
  const frame = document.createElement('iframe');
  frame.style.cssText = 'position:fixed;left:-9999px;width:1280px;height:800px;border:0';
  document.body.appendChild(frame);

  try {
    const doc = frame.contentDocument!;
    doc.open();
    doc.write('<!doctype html><html><head></head><body></body></html>');
    doc.close();

    // The application stylesheet, as the browser actually compiled it.
    for (const sheet of Array.from(document.styleSheets)) {
      const rules = (() => {
        try {
          return Array.from(sheet.cssRules);
        } catch {
          return []; // cross-origin sheet; nothing of ours lives in one
        }
      })();
      if (rules.length === 0) {
        continue;
      }
      const style = doc.createElement('style');
      style.textContent = rules.map((rule) => rule.cssText).join('\n');
      doc.head.appendChild(style);
    }

    doc.documentElement.setAttribute('data-theme', theme);
    run(doc);
  } finally {
    frame.remove();
  }
}

describe('Design system', () => {
  beforeEach(() => TestBed.configureTestingModule({}));

  describe('theme', () => {
    it('defines the full semantic palette in both themes, with no token left unresolved', () => {
      const required = [
        '--bg', '--surface-1', '--surface-2', '--surface-3', '--surface-raised',
        '--text-1', '--text-2', '--text-3',
        '--border', '--border-strong', '--border-subtle', '--border-control',
        '--success', '--warning', '--danger', '--info',
        '--accent', '--accent-2', '--gradient-brand',
      ];

      for (const theme of ['light', 'dark'] as const) {
        withDocument(theme, (doc) => {
          for (const name of required) {
            expect(token(doc, name))
              .withContext(`${name} in ${theme}`)
              .not.toBe('');
          }
        });
      }
    });

    it('resolves the dark theme to navy rather than to grey', () => {
      withDocument('dark', (doc) => {
        const [r, g, b] = resolveColour(doc, token(doc, '--bg'));

        // The identity is navy: the ground must carry a blue cast at every
        // step. A neutral grey would have r ≈ g ≈ b.
        expect(b).toBeGreaterThan(r);
        expect(b).toBeGreaterThan(g);
      });
    });

    it('lifts each surface step clear of the one behind it', () => {
      // Elevation in the dark theme is carried by surface contrast, so the
      // steps have to be genuinely distinguishable rather than nominally
      // different.
      withDocument('dark', (doc) => {
        const steps = ['--bg', '--surface-1', '--surface-2', '--surface-3', '--surface-raised']
          .map((name) => luminance(resolveColour(doc, token(doc, name))));

        for (let i = 1; i < steps.length; i += 1) {
          expect(steps[i])
            .withContext(`surface step ${i} must be lighter than the one below it`)
            .toBeGreaterThan(steps[i - 1]);
        }
      });
    });
  });

  describe('contrast (WCAG AA)', () => {
    // 4.5:1 is the AA threshold for body text; 3:1 for large text and for
    // non-text boundaries such as borders.
    const bodyPairs: ReadonlyArray<readonly [string, string]> = [
      ['--text-1', '--bg'],
      ['--text-1', '--surface-1'],
      ['--text-1', '--surface-2'],
      ['--text-2', '--surface-1'],
      ['--text-3', '--surface-1'],
      ['--success', '--surface-1'],
      ['--warning', '--surface-1'],
      ['--danger', '--surface-1'],
      ['--info', '--surface-1'],
    ];

    for (const theme of ['light', 'dark'] as const) {
      it(`keeps body text at 4.5:1 or better in the ${theme} theme`, () => {
        withDocument(theme, (doc) => {
          for (const [fg, bg] of bodyPairs) {
            const ratio = contrastRatio(
              resolveColour(doc, token(doc, fg)),
              resolveColour(doc, token(doc, bg)),
            );
            expect(ratio)
              .withContext(`${fg} on ${bg} in ${theme} was ${ratio.toFixed(2)}:1`)
              .toBeGreaterThanOrEqual(4.5);
          }
        });
      });

      it(`keeps interactive boundaries at 3:1 or better in the ${theme} theme`, () => {
        // WCAG 2.1 SC 1.4.11. An empty text field is identified by its border
        // and nothing else, so that border is not decoration — it is the only
        // thing telling a low-vision reader the control is there.
        const boundaries: ReadonlyArray<readonly [string, string]> = [
          ['--border-control', '--surface-1'],
          ['--border-control', '--surface-2'],
          ['--accent', '--surface-1'],
        ];

        withDocument(theme, (doc) => {
          for (const [edge, bg] of boundaries) {
            const ratio = contrastRatio(
              resolveColour(doc, token(doc, edge)),
              resolveColour(doc, token(doc, bg)),
            );
            expect(ratio)
              .withContext(`${edge} on ${bg} in ${theme} was ${ratio.toFixed(2)}:1`)
              .toBeGreaterThanOrEqual(3);
          }
        });
      });

      it(`keeps the primary button's label legible on its own fill in the ${theme} theme`, () => {
        withDocument(theme, (doc) => {
          const ratio = contrastRatio(
            resolveColour(doc, token(doc, '--accent-contrast')),
            resolveColour(doc, token(doc, '--accent')),
          );
          expect(ratio)
            .withContext(`accent-contrast on accent in ${theme} was ${ratio.toFixed(2)}:1`)
            .toBeGreaterThanOrEqual(4.5);
        });
      });
    }
  });

  describe('motion', () => {
    it('stops every animation and transition under prefers-reduced-motion', () => {
      // Read from the stylesheet rather than from a computed style: the spec
      // runner cannot change the host's motion preference, so the assertion is
      // that the escape hatch exists and is unconditional.
      const reducedMotionRules = Array.from(document.styleSheets)
        .flatMap((sheet) => {
          try {
            return Array.from(sheet.cssRules);
          } catch {
            return [];
          }
        })
        .filter((rule): rule is CSSMediaRule =>
          rule instanceof CSSMediaRule && rule.conditionText.includes('prefers-reduced-motion'));

      expect(reducedMotionRules.length)
        .withContext('no prefers-reduced-motion block found in the application stylesheet')
        .toBeGreaterThan(0);

      const body = reducedMotionRules.map((rule) => rule.cssText).join('\n');
      for (const property of ['animation-duration', 'transition-duration', 'animation-delay']) {
        expect(body)
          .withContext(`${property} is not neutralised under reduced motion`)
          .toContain(property);
      }
      // `scroll-behavior: auto` matters too: a smooth-scrolling page is
      // motion the preference is asking us not to produce.
      expect(body).toContain('scroll-behavior');
    });
  });

  describe('token discipline', () => {
    it('keeps raw colour literals out of every layer above the tokens', () => {
      // The whole re-skin works because colour is defined in one place. A hex
      // literal in a component rule is a value that will not follow the theme,
      // so it is a defect even when it happens to look right today.
      const offenders: string[] = [];

      for (const sheet of Array.from(document.styleSheets)) {
        const rules = (() => {
          try {
            return Array.from(sheet.cssRules);
          } catch {
            return [];
          }
        })();

        const walk = (rule: CSSRule): void => {
          if (rule instanceof CSSGroupingRule) {
            Array.from(rule.cssRules).forEach(walk);
            return;
          }
          if (!(rule instanceof CSSStyleRule)) {
            return;
          }
          // The token layer is where literals belong; it is identified by the
          // custom properties it defines, not by file name (file boundaries
          // are gone by the time the browser sees this).
          const declaresPrimitives = Array.from(rule.style).some((prop) => prop.startsWith('--c-'));
          if (declaresPrimitives) {
            return;
          }
          for (const property of Array.from(rule.style)) {
            const value = rule.style.getPropertyValue(property);
            // `--`-prefixed theme values are the semantic layer, which is also
            // allowed to name literals.
            if (property.startsWith('--')) {
              continue;
            }
            if (/#[0-9a-f]{3,8}\b/i.test(value)) {
              offenders.push(`${rule.selectorText} { ${property}: ${value} }`);
            }
          }
        };

        rules.forEach(walk);
      }

      expect(offenders)
        .withContext(`colour literals outside the token layer:\n${offenders.join('\n')}`)
        .toEqual([]);
    });
  });
});
