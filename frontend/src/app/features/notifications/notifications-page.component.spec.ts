import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { of, throwError } from 'rxjs';

import { NotificationsPageComponent } from './notifications-page.component';
import { AppNotification } from '../../core/models/notification.model';
import { NotificationService } from '../../core/services/notification.service';

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 1, notification_type: 'OD_REJECTED', title: 'OD rejected',
    message: 'Reason: not applicable.', related_entity_type: 'odrequest', related_entity_id: 3,
    action_route: '/student/od', priority: 'HIGH', is_read: false, read_at: null,
    created_at: '2026-09-15T10:00:00Z', ...overrides,
  };
}

describe('NotificationsPageComponent', () => {
  let notificationService: jasmine.SpyObj<NotificationService>;
  let unread: ReturnType<typeof signal<number>>;

  beforeEach(async () => {
    unread = signal(2);
    notificationService = jasmine.createSpyObj<NotificationService>(
      'NotificationService', ['list', 'markRead', 'markAllRead'], { unreadCount: unread.asReadonly() },
    );
    await TestBed.configureTestingModule({
      imports: [NotificationsPageComponent],
      providers: [provideRouter([]), { provide: NotificationService, useValue: notificationService }],
    }).compileComponents();
  });

  function setup(results: AppNotification[] = [notification()], extra = {}) {
    notificationService.list.and.returnValue(
      of({ results, count: results.length, next: null, previous: null, ...extra }),
    );
    const fixture = TestBed.createComponent(NotificationsPageComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('lists notifications with their type and read state', () => {
    const fixture = setup();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('OD rejected');
    expect(text).toContain('OD_REJECTED');
    expect(text).toContain('Unread');
  });

  it('shows an empty state', () => {
    const fixture = setup([]);
    expect(fixture.nativeElement.textContent).toContain('No notifications yet.');
  });

  it('shows a different empty state when filtering to unread', () => {
    const fixture = setup([]);
    fixture.componentInstance.toggleUnreadOnly();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No unread notifications.');
  });

  it('requests only unread when the filter is toggled on', () => {
    const fixture = setup();
    fixture.componentInstance.toggleUnreadOnly();
    expect(notificationService.list).toHaveBeenCalledWith(1, true);
  });

  it('marks one read and replaces the row', () => {
    const fixture = setup();
    notificationService.markRead.and.returnValue(of(notification({ is_read: true, read_at: 'x' })));
    fixture.componentInstance.markRead(notification());
    fixture.detectChanges();

    expect(notificationService.markRead).toHaveBeenCalledWith(1);
    expect(fixture.componentInstance.notifications()[0].is_read).toBeTrue();
  });

  it('does not re-mark an already-read notification', () => {
    const fixture = setup([notification({ is_read: true })]);
    fixture.componentInstance.markRead(notification({ is_read: true }));
    expect(notificationService.markRead).not.toHaveBeenCalled();
  });

  it('marks all read and reloads', () => {
    const fixture = setup();
    notificationService.markAllRead.and.returnValue(of({ marked_read: 2 }));
    notificationService.list.calls.reset();

    fixture.componentInstance.markAllRead();
    expect(notificationService.markAllRead).toHaveBeenCalled();
    expect(notificationService.list).toHaveBeenCalled();
  });

  it('navigates to the internal action route when opened', () => {
    const fixture = setup();
    notificationService.markRead.and.returnValue(of(notification({ is_read: true })));
    const navigate = spyOn(TestBed.inject(Router), 'navigateByUrl');

    fixture.componentInstance.open(notification());
    expect(navigate).toHaveBeenCalledWith('/student/od');
  });

  it('pages forward only when the backend says there is a next page', () => {
    const fixture = setup([notification()], { next: 'http://x/?page=2' });
    notificationService.list.calls.reset();
    fixture.componentInstance.nextPage();
    expect(notificationService.list).toHaveBeenCalledWith(2, false);

    const last = setup([notification()], { next: null });
    notificationService.list.calls.reset();
    last.componentInstance.nextPage();
    expect(notificationService.list).not.toHaveBeenCalled();
  });

  it('shows an error state when loading fails', () => {
    notificationService.list.and.returnValue(throwError(() => ({ status: 500 })));
    const fixture = TestBed.createComponent(NotificationsPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load');
  });

  it('colours badges by outcome', () => {
    const fixture = setup();
    const component = fixture.componentInstance;
    expect(component.badgeClass('ATTENDANCE_APPROVED')).toContain('success');
    expect(component.badgeClass('OD_REJECTED')).toContain('danger');
    expect(component.badgeClass('EVIDENCE_RESUBMISSION_REQUIRED')).toContain('warning');
  });
});
