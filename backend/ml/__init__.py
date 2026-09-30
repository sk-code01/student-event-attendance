"""
Pure model code: numpy in, numpy out.

Nothing in this package imports Django or touches the database. Feature
extraction (which does query the ORM) lives in `apps.ai.features`; this package
only fits and scores. That separation is what lets each model be unit-tested
against a handful of hand-written arrays, and what keeps a scikit-learn failure
isolated behind the `apps.ai.services` fallback boundary.

Every model here is **decision support**. None of them approves, rejects,
verifies, registers or overrides anything — they return scores, ranks and
labels for a human to weigh.
"""
