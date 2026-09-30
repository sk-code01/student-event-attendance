import { HttpErrorResponse } from '@angular/common/http';

import { AiReason } from '../../core/models/ai.model';

/**
 * Shared wording for the non-result states of every AI view. Kept in one
 * place so a Student and an Event Coordinator read the same explanation for the same
 * backend reason code, and so no view invents a more confident message than
 * the backend actually returned.
 */
export function reasonMessage(reason: AiReason | undefined, detail?: string): string {
  switch (reason) {
    case 'INSUFFICIENT_DATA':
      return detail || 'Not enough data yet for this model to produce a meaningful signal.';
    case 'MODEL_ERROR':
      return detail || 'The model could not run just now. Nothing else in the system is affected.';
    case 'NO_ACTIONABLE_EVENTS':
      return detail || 'There are no events open for registration that you have not already registered for.';
    default:
      return detail || 'This signal is not available right now.';
  }
}

export function httpErrorMessage(error: unknown): string {
  const status = (error as HttpErrorResponse | undefined)?.status;
  if (status === 403) {
    return 'This view is not available for your role.';
  }
  if (status === 404) {
    return 'That record is not within your scope.';
  }
  return 'Unable to load this signal. Nothing else in the system is affected.';
}

/** Bootstrap contextual class for a LOW / MODERATE|MEDIUM / HIGH label. */
export function levelClass(level: string | null | undefined): string {
  switch (level) {
    case 'HIGH':
      return 'text-bg-danger';
    case 'MEDIUM':
    case 'MODERATE':
      return 'text-bg-warning';
    case 'LOW':
      return 'text-bg-success';
    default:
      return 'text-bg-secondary';
  }
}

/** Engagement labels are the reverse of risk: HIGH engagement is good. */
export function engagementClass(level: string | null | undefined): string {
  switch (level) {
    case 'HIGH':
      return 'text-bg-success';
    case 'MODERATE':
      return 'text-bg-primary';
    case 'LOW':
      return 'text-bg-secondary';
    default:
      return 'text-bg-light';
  }
}
