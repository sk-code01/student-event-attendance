import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'seams_theme';

/**
 * Light / dark / system theme.
 *
 * The preference and the *resolved* theme are deliberately separate signals.
 * "System" is a preference, not a colour — it resolves to light or dark from
 * the OS and must keep tracking it, so a user who picked System and then
 * changes their OS at dusk sees the app follow without reloading.
 *
 * The resolved value is written to `<html data-theme>`, which is the single
 * hook every token in the stylesheet keys off. Nothing else needs to know
 * which theme is active.
 *
 * The initial value is also applied by a tiny inline script in index.html,
 * before Angular boots. That is what prevents the white flash on load that a
 * service-only approach always has.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);

  private readonly _preference = signal<ThemePreference>(this.readStoredPreference());
  readonly preference = this._preference.asReadonly();

  /** What the OS currently reports; only consulted when preference is 'system'. */
  private readonly systemPrefersDark = signal(this.queryPrefersDark());

  readonly resolved = computed<ResolvedTheme>(() => {
    const preference = this._preference();
    if (preference === 'system') {
      return this.systemPrefersDark() ? 'dark' : 'light';
    }
    return preference;
  });

  constructor() {
    const media = this.mediaQuery();
    if (media) {
      // Keep following the OS while the preference is 'system'. `change`
      // fires on the OS switching, not on our own toggle.
      media.addEventListener('change', (event) => this.systemPrefersDark.set(event.matches));
    }
    this.apply(this.resolved());
  }

  set(preference: ThemePreference): void {
    this._preference.set(preference);
    this.writeStoredPreference(preference);
    this.apply(this.resolved());
  }

  /** Cycles light -> dark -> system, which is what the header control does. */
  cycle(): ThemePreference {
    const order: ThemePreference[] = ['light', 'dark', 'system'];
    const next = order[(order.indexOf(this._preference()) + 1) % order.length];
    this.set(next);
    return next;
  }

  private apply(theme: ResolvedTheme): void {
    this.document.documentElement.setAttribute('data-theme', theme);
  }

  private mediaQuery(): MediaQueryList | null {
    const view = this.document.defaultView;
    return view?.matchMedia ? view.matchMedia('(prefers-color-scheme: dark)') : null;
  }

  private queryPrefersDark(): boolean {
    return this.mediaQuery()?.matches ?? false;
  }

  private readStoredPreference(): ThemePreference {
    try {
      const stored = this.document.defaultView?.localStorage.getItem(STORAGE_KEY);
      if (stored === 'light' || stored === 'dark' || stored === 'system') {
        return stored;
      }
    } catch {
      /* Storage can throw in private mode; the default below costs the user
         nothing and is corrected the moment they choose. */
    }
    // Dark is the product's default (requirement 4), so a first-time visitor
    // sees the intended design rather than whatever their OS happens to be
    // set to. Choosing "System" explicitly still hands control back to the OS.
    return 'dark';
  }

  private writeStoredPreference(preference: ThemePreference): void {
    try {
      this.document.defaultView?.localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      /* Preference simply will not persist. Not worth failing the toggle. */
    }
  }
}
