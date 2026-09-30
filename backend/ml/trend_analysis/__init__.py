"""
Statistical trend analysis.

Deliberately empty of new code: the project's trend analysis already lives in
`apps.analytics.trends` (Phase 7) — period-over-period change, direction,
moving average — and it is plain arithmetic, not a model. Re-implementing it
here would create two disagreeing sources. Phase 8 consumes that module where
it needs a trend; this package exists so the `ml/` layout matches the SRS and
the location is documented rather than left as a question.
"""
