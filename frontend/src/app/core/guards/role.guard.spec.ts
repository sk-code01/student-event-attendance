import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { UrlTree, provideRouter } from '@angular/router';

import { roleGuard } from './role.guard';
import { AuthService } from '../services/auth.service';

describe('roleGuard', () => {
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    authService = TestBed.inject(AuthService);
  });

  function run(...roles: ('STUDENT' | 'FACULTY' | 'EVENT_COORDINATOR' | 'ADMIN')[]): boolean | UrlTree {
    const guard = roleGuard(...roles);
    return TestBed.runInInjectionContext(() => guard({} as never, {} as never)) as boolean | UrlTree;
  }

  it('redirects unauthenticated users to /login', () => {
    spyOn(authService, 'isAuthenticated').and.returnValue(false);
    const result = run('ADMIN');
    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/login');
  });

  it('allows access when the user has an allowed role', () => {
    spyOn(authService, 'isAuthenticated').and.returnValue(true);
    spyOn(authService, 'hasRole').and.returnValue(true);
    expect(run('STUDENT')).toBeTrue();
  });

  it('redirects to /unauthorized when the user lacks an allowed role', () => {
    spyOn(authService, 'isAuthenticated').and.returnValue(true);
    spyOn(authService, 'hasRole').and.returnValue(false);
    const result = run('ADMIN');
    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/unauthorized');
  });
});
