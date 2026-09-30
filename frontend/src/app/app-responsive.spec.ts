import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';
import { Role, User } from './core/models/user.model';
import { AuthService } from './core/services/auth.service';
import { NotificationService } from './core/services/notification.service';
import { ThemeService } from './core/services/theme.service';

/**
 * Responsive and role-differentiation checks for the application shell.
 *
 * These run in real Chrome, so they measure actual layout rather than
 * asserting that a class name is present. The rule they exist to defend is
 * the one that is easiest to break and hardest to notice: **the page itself
 * must never scroll sideways**. Wide content scrolls inside its own
 * container; the document does not.
 *
 * The overflow check deliberately renders inside an iframe rather than a
 * fixed-width `<div>`. A media query is evaluated against the *viewport*, so
 * a narrow host element inside a wide Karma window still gets the desktop
 * layout — which makes a div-based test pass at 320px while the real phone
 * is broken. An iframe has a viewport of its own, so `@media (max-width:
 * 991.98px)` resolves exactly as it would on the device.
 *
 * Widths cover the representative targets from phone to large desktop.
 */

const WIDTHS = [320, 375, 390, 414, 768, 820, 1024, 1280, 1366, 1440, 1600, 1920, 2560];

/**
 * The host document's CSS, flattened to a single string. The rules are read
 * out of `document.styleSheets` rather than re-fetched so a measurement frame
 * is styled synchronously — a `<link>` would still be loading when the first
 * measurement is taken. Built once; every frame reuses it.
 */
let cachedCss: string | null = null;

function hostCss(): string {
  if (cachedCss !== null) {
    return cachedCss;
  }
  const css: string[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      for (const rule of Array.from(sheet.cssRules)) {
        css.push(rule.cssText);
      }
    } catch {
      // A cross-origin sheet cannot be read. None of ours are, so skipping is
      // safe; it would only ever be an injected third-party sheet.
    }
  }
  // Transitions off: a computed value read while one is running is the
  // interpolated value, not the one the rule asks for.
  css.push('*, *::before, *::after { transition: none !important; animation: none !important; }');
  cachedCss = css.join('\n');
  return cachedCss;
}

/**
 * Renders `element` inside a brand-new iframe of exactly `width`, and hands
 * back the frame's document.
 *
 * A fresh frame per width rather than one frame resized repeatedly: resizing
 * does not restyle the child document synchronously — Chrome defers that to
 * the frame's next rendering update — so measurements taken after a resize
 * read a half-updated layout. A frame created at its final width has only
 * ever had one viewport, so there is nothing stale to read.
 */
function renderInFrame(host: HTMLElement, element: HTMLElement, width: number, role: Role): {
  frame: HTMLIFrameElement;
  doc: Document;
} {
  const frame = document.createElement('iframe');
  frame.style.cssText = `border:0;height:800px;width:${width}px;`;
  host.appendChild(frame);

  const doc = frame.contentDocument!;
  const style = doc.createElement('style');
  style.textContent = hostCss();
  doc.head.appendChild(style);
  doc.documentElement.setAttribute('data-role', role);
  doc.documentElement.setAttribute('data-theme', 'light');
  doc.body.style.margin = '0';
  doc.body.appendChild(doc.adoptNode(element));

  return { frame, doc };
}

function makeUser(role: Role): User {
  return {
    id: 1,
    username: 'testuser',
    email: 'testuser@example.com',
    role,
    department: { id: 1, name: 'Master of Computer Applications', code: 'MCA', is_active: true, created_at: '' },
    is_active: true,
    date_joined: '2026-01-01T00:00:00Z',
  } as User;
}

describe('App shell — responsive and role differentiation', () => {
  let authService: AuthService;
  let httpMock: HttpTestingController;
  let host: HTMLDivElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        ThemeService,
        NotificationService,
      ],
    }).compileComponents();

    authService = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);

    // A fixed-width host lets each width be measured without resizing the
    // Karma browser window, which the runner owns.
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => {
    host.remove();
    // The shell polls for the unread count once authenticated; drain it so a
    // stray request does not fail verification.
    httpMock.match(() => true).forEach((request) => request.flush({ unread: 0 }));
    httpMock.verify();
    TestBed.inject(NotificationService).stopPolling();
  });

  function renderAs(role: Role): ComponentFixture<App> {
    const fixture = TestBed.createComponent(App);
    (authService as unknown as { _currentUser: { set(value: User): void } })._currentUser.set(makeUser(role));
    fixture.detectChanges();
    host.appendChild(fixture.nativeElement);
    return fixture;
  }

  it('never lets the document scroll horizontally, at any supported width', () => {
    for (const role of ['ADMIN', 'EVENT_COORDINATOR', 'FACULTY', 'STUDENT'] as Role[]) {
      const fixture = renderAs(role);
      const element = fixture.nativeElement as HTMLElement;

      for (const width of WIDTHS) {
        const { frame, doc } = renderInFrame(host, element, width, role);
        fixture.detectChanges();

        // What a user experiences as a sideways-scrolling page is the
        // document scrolling, so that is what is measured — not one element
        // which may well be clipping its own overflow.
        const scrollWidth = Math.max(doc.documentElement.scrollWidth, doc.body.scrollWidth);
        // 1px of tolerance for sub-pixel rounding at fractional device ratios.
        expect(scrollWidth)
          .withContext(`${role}: horizontal overflow at ${width}px`)
          .toBeLessThanOrEqual(width + 1);

        // Proof that the frame really is acting as a viewport rather than a
        // narrow box inside a wide one: the sidebar is off-canvas below the
        // 992px breakpoint and in the layout above it. Without this the check
        // above could pass merely because the desktop layout happens to fit —
        // which is exactly how a fixed-width host element gives a false pass.
        const sidebar = doc.querySelector('.app-sidebar') as HTMLElement;
        const left = sidebar.getBoundingClientRect().left;
        if (width < 992) {
          expect(left).withContext(`${role}: sidebar off-canvas at ${width}px`).toBeLessThan(0);
        } else {
          expect(left).withContext(`${role}: sidebar in-flow at ${width}px`).toBe(0);
        }

        frame.remove();
      }

      fixture.destroy();
    }
  });

  it('renders the sidebar and header for every role', () => {
    for (const role of ['ADMIN', 'EVENT_COORDINATOR', 'FACULTY', 'STUDENT'] as Role[]) {
      const fixture = renderAs(role);
      const element = fixture.nativeElement as HTMLElement;
      expect(element.querySelector('.app-sidebar')).withContext(role).not.toBeNull();
      expect(element.querySelector('.app-header')).withContext(role).not.toBeNull();
      expect(element.querySelector('.app-content')).withContext(role).not.toBeNull();
      fixture.destroy();
    }
  });

  it('gives each role its own navigation, not a shared one', () => {
    const navFor = (role: Role): string[] => {
      const fixture = renderAs(role);
      const labels = Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('.nav-label'),
      ).map((el) => (el.textContent ?? '').trim());
      fixture.destroy();
      return labels;
    };

    const admin = navFor('ADMIN');
    const eventCoordinator = navFor('EVENT_COORDINATOR');
    const faculty = navFor('FACULTY');
    const student = navFor('STUDENT');

    // Each role has something the others do not — the navigation is genuinely
    // per-role rather than one list with items hidden.
    expect(admin).toContain('Colleges');
    expect(eventCoordinator).toContain('Attendance');
    expect(faculty).toContain('Verification Queue');
    expect(student).toContain('Browse Events');

    expect(student).not.toContain('Colleges');
    expect(faculty).not.toContain('Colleges');
    expect(student).not.toContain('Verification Queue');
  });

  it('stamps the role on the document so the role theme is selected', () => {
    for (const role of ['ADMIN', 'EVENT_COORDINATOR', 'FACULTY', 'STUDENT'] as Role[]) {
      const fixture = renderAs(role);
      expect(document.documentElement.getAttribute('data-role')).toBe(role);
      fixture.destroy();
    }
  });

  it('resolves one shared accent identity for every role', () => {
    // This replaced an earlier rule that each role had its own accent hue.
    // The product now has a single visual identity — navy, purple and
    // electric blue — and what differs between roles is the information a
    // page shows, not its colour. Asserted because a stray per-role override
    // would be invisible until someone compared two screenshots side by side.
    const accents = new Set<string>();
    for (const role of ['ADMIN', 'EVENT_COORDINATOR', 'FACULTY', 'STUDENT'] as Role[]) {
      const fixture = renderAs(role);
      accents.add(getComputedStyle(document.documentElement).getPropertyValue('--accent').trim());
      fixture.destroy();
    }
    expect(accents.size).withContext(`accents seen: ${[...accents]}`).toBe(1);
  });

  it('still gives each role its own navigation, which is what does differ', () => {
    // The counterpart to the assertion above: sharing an identity must not
    // quietly turn into sharing a menu.
    const labelsFor = (role: Role): string[] => {
      const fixture = renderAs(role);
      const labels = Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('.nav-label'),
      ).map((el) => (el.textContent ?? '').trim());
      fixture.destroy();
      return labels;
    };

    expect(labelsFor('ADMIN')).not.toEqual(labelsFor('STUDENT'));
  });

  it('collapses the sidebar to an icon rail without losing the link text for assistive tech', () => {
    const fixture = renderAs('ADMIN');
    fixture.componentInstance.collapsed.set(true);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.app-shell')?.classList).toContain('is-collapsed');
    // The label is visually hidden, not removed: a collapsed icon must still
    // have an accessible name.
    const label = element.querySelector('.nav-label') as HTMLElement;
    expect(label).not.toBeNull();
    expect((label.textContent ?? '').trim().length).toBeGreaterThan(0);
  });

  it('opens and closes the mobile navigation', () => {
    const fixture = renderAs('STUDENT');
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-sidebar')?.classList).not.toContain('is-open');

    fixture.componentInstance.toggleMobileNav();
    fixture.detectChanges();
    expect(element.querySelector('.app-sidebar')?.classList).toContain('is-open');
    expect(element.querySelector('.nav-scrim')).not.toBeNull();

    fixture.componentInstance.closeMobileNav();
    fixture.detectChanges();
    expect(element.querySelector('.app-sidebar')?.classList).not.toContain('is-open');
  });

  it('offers a skip link as the first focusable element', () => {
    const fixture = renderAs('FACULTY');
    const element = fixture.nativeElement as HTMLElement;
    const skip = element.querySelector('.skip-link') as HTMLAnchorElement;
    expect(skip).not.toBeNull();
    expect(skip.getAttribute('href')).toBe('#main-content');
    expect(element.querySelector('#main-content')).not.toBeNull();
  });

  it('exposes the landmark regions assistive technology navigates by', () => {
    const fixture = renderAs('ADMIN');
    const element = fixture.nativeElement as HTMLElement;

    // Navigation, header and main content are the three regions a screen
    // reader user jumps between; each must be a real landmark, not a div.
    const nav = element.querySelector('nav');
    expect(nav).not.toBeNull();
    expect(nav!.getAttribute('aria-label')).toBeTruthy();
    expect(element.querySelector('header')).not.toBeNull();

    const main = element.querySelector('main');
    expect(main).not.toBeNull();
    expect(main!.id).toBe('main-content');
    // Focusable by script so the skip link actually moves focus, not just the
    // scroll position.
    expect(main!.getAttribute('tabindex')).toBe('-1');
  });

  it('gives every control in the shell an accessible name', () => {
    const fixture = renderAs('STUDENT');
    const element = fixture.nativeElement as HTMLElement;

    const controls = element.querySelectorAll('button, a, input, select');
    const unnamed: string[] = [];
    controls.forEach((control) => {
      const named =
        control.hasAttribute('aria-label') ||
        control.hasAttribute('aria-labelledby') ||
        (control.textContent ?? '').trim().length > 0;
      if (!named) {
        unnamed.push(control.outerHTML.slice(0, 80));
      }
    });
    expect(unnamed).withContext(`unnamed controls: ${unnamed.join(' | ')}`).toEqual([]);
  });

  it('cycles the theme through light, dark and system', () => {
    const fixture = renderAs('EVENT_COORDINATOR');
    const theme = TestBed.inject(ThemeService);

    theme.set('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    fixture.componentInstance.cycleTheme();
    expect(theme.preference()).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

    fixture.componentInstance.cycleTheme();
    expect(theme.preference()).toBe('system');
    // System resolves to a concrete value; it never leaves data-theme unset.
    expect(['light', 'dark']).toContain(document.documentElement.getAttribute('data-theme')!);
  });
});
