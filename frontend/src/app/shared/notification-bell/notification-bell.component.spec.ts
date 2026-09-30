import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { signal } from '@angular/core';

import { NotificationBellComponent } from './notification-bell.component';
import { AppNotification } from '../../core/models/notification.model';
import { NotificationService } from '../../core/services/notification.service';

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 1, notification_type: 'ATTENDANCE_APPROVED', title: 'Attendance approved',
    message: 'Your attendance was approved.', related_entity_type: 'attendance',
    related_entity_id: 5, action_route: '/student/attendance', priority: 'HIGH',
    is_read: false, read_at: null, created_at: '2026-09-15T10:00:00Z', ...overrides,
  };
}

const page = <T,>(results: T[]) => ({ results, count: results.length, next: null, previous: null });

describe('NotificationBellComponent', () => {
  let notificationService: jasmine.SpyObj<NotificationService>;
  let unread: ReturnType<typeof signal<number>>;

  beforeEach(async () => {
    unread = signal(0);
    notificationService = jasmine.createSpyObj<NotificationService>(
      'NotificationService', ['list', 'markRead', 'markAllRead'], { unreadCount: unread.asReadonly() },
    );
    await TestBed.configureTestingModule({
      imports: [NotificationBellComponent],
      providers: [provideRouter([]), { provide: NotificationService, useValue: notificationService }],
    }).compileComponents();
  });

  it('shows the unread badge only when there is something unread', () => {
    notificationService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.icon-btn-badge')).toBeNull();

    unread.set(4);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.icon-btn-badge').textContent.trim()).toBe('4');
  });

  it('carries the unread count in the accessible name, not only in the badge', () => {
    // The control is icon-only, so a screen reader has nothing to read unless
    // the count is in the label.
    notificationService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button').getAttribute('aria-label')).toBe('Notifications');

    unread.set(3);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button').getAttribute('aria-label'))
      .toBe('3 unread notifications');
  });

  it('loads recent notifications only when the panel is opened', () => {
    notificationService.list.and.returnValue(of(page([notification()])));
    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.detectChanges();
    expect(notificationService.list).not.toHaveBeenCalled();

    fixture.componentInstance.toggle();
    fixture.detectChanges();
    expect(notificationService.list).toHaveBeenCalledTimes(1);
    expect(fixture.nativeElement.textContent).toContain('Attendance approved');
  });

  it('shows an empty state', () => {
    notificationService.list.and.returnValue(of(page([])));
    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.componentInstance.toggle();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No notifications yet.');
  });

  it('shows an error state when loading fails', () => {
    notificationService.list.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.componentInstance.toggle();
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });

  it('marks unread notifications read and navigates to the internal route', () => {
    notificationService.list.and.returnValue(of(page([notification()])));
    notificationService.markRead.and.returnValue(of(notification({ is_read: true })));
    const router = TestBed.inject(Router);
    const navigate = spyOn(router, 'navigateByUrl');

    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.componentInstance.toggle();
    fixture.detectChanges();
    fixture.componentInstance.openNotification(notification());

    expect(notificationService.markRead).toHaveBeenCalledWith(1);
    expect(navigate).toHaveBeenCalledWith('/student/attendance');
  });

  it('does not re-mark an already-read notification', () => {
    notificationService.list.and.returnValue(of(page([notification({ is_read: true })])));
    const router = TestBed.inject(Router);
    const navigate = spyOn(router, 'navigateByUrl');

    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.componentInstance.toggle();
    fixture.componentInstance.openNotification(notification({ is_read: true }));

    expect(notificationService.markRead).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith('/student/attendance');
  });

  it('still navigates when marking read fails, rather than trapping the user', () => {
    notificationService.list.and.returnValue(of(page([notification()])));
    notificationService.markRead.and.returnValue(throwError(() => ({ status: 500 })));
    const router = TestBed.inject(Router);
    const navigate = spyOn(router, 'navigateByUrl');

    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.componentInstance.toggle();
    fixture.componentInstance.openNotification(notification());

    expect(navigate).toHaveBeenCalledWith('/student/attendance');
  });

  it('marks all read from the panel', () => {
    notificationService.list.and.returnValue(of(page([notification()])));
    notificationService.markAllRead.and.returnValue(of({ marked_read: 1 }));

    const fixture = TestBed.createComponent(NotificationBellComponent);
    fixture.componentInstance.toggle();
    fixture.componentInstance.markAllRead();
    fixture.detectChanges();

    expect(notificationService.markAllRead).toHaveBeenCalled();
    expect(fixture.componentInstance.recent()[0].is_read).toBeTrue();
  });
});
