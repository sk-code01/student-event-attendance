import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';
import { environment } from '../environments/environment';
import { AuthService } from './core/services/auth.service';
import { NotificationService } from './core/services/notification.service';
import { User } from './core/models/user.model';

const MOCK_USER: User = {
  id: 1,
  username: 'alice',
  full_name: 'Alice',
  university_registration_number: null,
  faculty_id: null,
  email: 'alice@example.com',
  role: 'STUDENT',
  department: null,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
};

describe('App', () => {
  let httpMock: HttpTestingController;
  let notificationService: NotificationService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    notificationService = TestBed.inject(NotificationService);
  });

  afterEach(() => {
    // The shell starts a polling timer once authenticated; stop it so the
    // interval does not leak into the next spec.
    notificationService.stopPolling();
    httpMock.verify();
  });

  /** Authenticates and satisfies the unread-count request the shell fires as
   * soon as it sees an authenticated user (Phase 6 notification polling). */
  function authenticate(fixture: ReturnType<typeof TestBed.createComponent>) {
    const authService = TestBed.inject(AuthService);
    authService.fetchCurrentUser().subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/users/me/`).flush(MOCK_USER);

    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/unread-count/`).flush({ unread: 0 });
    fixture.detectChanges();
  }

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('does not show the nav bar when unauthenticated', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('nav')).toBeNull();
  });

  it('does not poll for notifications while unauthenticated', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    httpMock.expectNone(`${environment.apiBaseUrl}/notifications/unread-count/`);
  });

  it('shows the shell with the username and a readable role once the current user is loaded', () => {
    const fixture = TestBed.createComponent(App);
    authenticate(fixture);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('nav')).not.toBeNull();
    expect(compiled.textContent).toContain('alice');
    // The shell presents the human-readable label ("Student") rather than the
    // raw enum; the enum value itself is still shown in the profile menu.
    expect(compiled.textContent).toContain('Student');
    expect(compiled.querySelector('.app-sidebar')).not.toBeNull();
    expect(compiled.querySelector('.app-header')).not.toBeNull();
  });

  it('applies the role to the document so the role theme is selected', () => {
    const fixture = TestBed.createComponent(App);
    authenticate(fixture);
    expect(document.documentElement.getAttribute('data-role')).toBe('STUDENT');
  });

  it('shows only the navigation sections for the signed-in role', () => {
    const fixture = TestBed.createComponent(App);
    authenticate(fixture);

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Browse Events');      // student navigation
    expect(text).not.toContain('Colleges');       // admin-only
    expect(text).not.toContain('Verification Queue'); // faculty-only
  });

  it('renders the notification centre in the authenticated shell', () => {
    const fixture = TestBed.createComponent(App);
    authenticate(fixture);

    const compiled = fixture.nativeElement as HTMLElement;
    const bell = compiled.querySelector('app-notification-bell');
    expect(bell).not.toBeNull();
    // The control is an icon button now, so its name is the accessible name
    // rather than visible text -- which is the thing that actually matters.
    expect(bell?.querySelector('button')?.getAttribute('aria-label')).toContain('Notifications');
  });

  it('offers a working profile menu with profile, password and logout', () => {
    const fixture = TestBed.createComponent(App);
    authenticate(fixture);

    fixture.componentInstance.toggleProfile();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const hrefs = Array.from(compiled.querySelectorAll('[role="menuitem"]'))
      .map((el) => el.getAttribute('href'));
    expect(hrefs).toContain('/profile');
    expect(hrefs).toContain('/profile/password');
    expect(compiled.textContent).toContain('Logout');
  });

  it('starts notification polling once authenticated', () => {
    const fixture = TestBed.createComponent(App);
    const startSpy = spyOn(notificationService, 'startPolling').and.callThrough();

    const authService = TestBed.inject(AuthService);
    authService.fetchCurrentUser().subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/users/me/`).flush(MOCK_USER);
    fixture.detectChanges();

    expect(startSpy).toHaveBeenCalled();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/unread-count/`).flush({ unread: 3 });
    expect(notificationService.unreadCount()).toBe(3);
  });
});
