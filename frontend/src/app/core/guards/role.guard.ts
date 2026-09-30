import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../services/auth.service';
import { Role } from '../models/user.model';

/** UX-level routing only. The Django API is the real security boundary —
 * every protected endpoint independently re-checks role/department, so a
 * user can never gain access simply by reaching a route past this guard. */
export function roleGuard(...allowedRoles: Role[]): CanActivateFn {
  return () => {
    const authService = inject(AuthService);
    const router = inject(Router);

    if (!authService.isAuthenticated()) {
      return router.createUrlTree(['/login']);
    }
    if (authService.hasRole(...allowedRoles)) {
      return true;
    }
    return router.createUrlTree(['/unauthorized']);
  };
}
