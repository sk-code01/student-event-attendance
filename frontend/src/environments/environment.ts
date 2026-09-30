export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000/api/v1',
  /**
   * How long a signed-in user may be idle before the session is ended.
   *
   * Configured here, in one place, rather than in the components that observe
   * activity — the timer itself lives in SessionService. This is the client's
   * own idle policy; the authoritative limits remain the JWT lifetimes the
   * backend issues and validates.
   */
  sessionInactivityTimeoutMinutes: 30,
};
