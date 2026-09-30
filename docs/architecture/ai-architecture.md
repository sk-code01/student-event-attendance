# AI / ML Architecture

## Position of the AI layer

The AI layer is **decision support only**. It ranks, scores and labels; it never
verifies evidence, never approves attendance or OD, never creates or approves an
achievement, and never changes any record. Every academic decision in this
system is taken by a person.

Three properties enforce that in code rather than by convention:

1. **Read-only, GET-only.** Every AI endpoint is a `GET`. No AI function writes
   to the database.
2. **No business service calls into `apps.ai`.** Registration, participation,
   verification, attendance, OD, achievement and notification services have no
   import of the AI module. An AI failure therefore has no transaction to roll
   back — that is a structural guarantee, and the workflow-safety tests pin it.
3. **A failure boundary on every entry point.** `_decision_support` in
   `apps/ai/services.py` wraps each public function. `InsufficientData` becomes
   `available: false, reason: "INSUFFICIENT_DATA"`; any other exception is
   logged with its traceback server-side and becomes
   `available: false, reason: "MODEL_ERROR"`. The caller never sees a Python
   error, and the core workflow is unaffected either way.

Every response carries the same disclaimer string:

> AI-generated decision-support signal. Final academic decisions remain with
> authorized Faculty/HOD personnel.

## Scope and data isolation

`apps/ai/features.py` is the only place in the AI layer that touches the ORM,
and every scoped query goes through `apps.analytics.scope.AnalyticsScope` — the
same boundary the analytics and report endpoints use. An AI endpoint therefore
cannot show a caller anything their role could not already aggregate.

The features themselves are counts, distances, durations and categories. No
password, token, storage key, file path, raw image or biometric data is read.
There is **no face recognition and no image analysis of any kind** — the models
never see an image.

## 1. Event recommendation — K-Nearest Neighbours

| | |
|---|---|
| Module | `ml/recommendation/knn.py`, orchestrated by `apps.ai.services.recommend_events` |
| Endpoint | `GET /api/v1/recommendations/` |
| Scope | The calling student only. There is no parameter by which to name another student. |
| Model version | `knn-similarity-v1` |
| Feature version | `features-v1` |

**Purpose.** Rank events currently open for registration by how close they are,
in feature space, to events the student has actually engaged with.

**Inputs.** A weighted vector per event: one-hot category (weight 1.0),
department match (0.6), current registration popularity (0.4), how soon the
event is within a 90-day horizon (0.3).

**Output.** A similarity score in `(0, 1]` per candidate, plus feature-backed
reasons, sorted by score, then soonest date, then id.

> **The score is a similarity, not a probability.** 1.0 means "identical, in
> feature space, to something this student already did". It is comparable within
> one response and means nothing as an absolute likelihood of attendance. The
> API says so in its own `score_basis` field.

**Cold start.** A student with no history does not get a KNN result. They get a
documented deterministic ranking — `0.5 × department match + 0.3 × normalised
popularity + 0.2 × how soon` — and the response reports `model: "cold_start"`,
`model_version: "cold-start-v1"` and a `score_basis` saying it is not a model
output. Nothing is passed off as a prediction that is not one.

**Minimum data.** One historical engaged event (`MIN_HISTORY_FOR_KNN = 1`).
When there are no open events to recommend, the response is `available: true`
with `reason: "NO_ACTIONABLE_EVENTS"` and an empty result list — an honest empty
answer rather than a failure.

**Determinism.** KNN has no random state. Identical inputs always produce an
identical ranking, which is what makes the behaviour testable.

## 2. Evidence risk signal — Isolation Forest

| | |
|---|---|
| Module | `ml/anomaly_detection/isolation_forest.py`, orchestrated by `apps.ai.services.evidence_risk_signals` |
| Endpoint | `GET /api/v1/anomalies/` |
| Scope | Rows inside the caller's `AnalyticsScope`. A Student may call it and sees signals on their own evidence only; an `evidence_id` outside the caller's scope is a `404` at the view layer, before any model runs. |
| Model version | `isolation-forest-v1` |
| Minimum data | 5 evidence records (`MIN_SAMPLES`), below which `INSUFFICIENT_DATA` |

**Purpose.** Point a reviewer at the evidence records whose metadata is most
unlike the rest of the population, so limited review attention goes where it is
most likely to matter.

**Inputs** (nine features, each with its temporal status declared, because an
anomaly model must not "predict" a decision using information that decision
created):

| Feature | Temporal status |
|---------|-----------------|
| `capture_count` | PRE-VERIFICATION |
| `version_count` | HISTORICAL |
| `max_venue_distance_m` | PRE-VERIFICATION |
| `mean_venue_distance_m` | PRE-VERIFICATION |
| `mean_gps_accuracy_m` | PRE-VERIFICATION |
| `mean_upload_delay_s` | PRE-VERIFICATION |
| `location_warning_ratio` | PRE-VERIFICATION |
| `prior_submissions` | HISTORICAL |
| `prior_rejection_ratio` | HISTORICAL — decided *before* this record existed |

No OUTCOME feature (the decision on this record) is ever an input.

**Output.** A `risk_level` of `LOW` / `MEDIUM` / `HIGH`, an `anomaly_score`, the
population thresholds that produced the level, the feature values, and
human-readable `signals` that are emitted only when a feature actually exceeds a
stated threshold.

**Level rule** (returned in the response, not hidden): `HIGH` = flagged as an
outlier by the forest **and** score ≥ the 90th percentile of the population;
`MEDIUM` = either one; otherwise `LOW`. Thresholds are percentiles of the
fitted population's own score distribution, so a level is always a statement
about *this dataset*, never an absolute claim about a record.

> **This is not proof of fraud.** There are no ground-truth "fraudulent" labels
> anywhere in this system, so no accuracy, precision or recall can honestly be
> quoted, and none is. A HIGH signal means "unusual, look at it"; it is not
> evidence of wrongdoing and must never be treated as a reason to reject.

**Fairness note.** The forest is fitted on the whole evidence population using
an identity-free feature matrix, so a level means the same thing regardless of
who asks; only rows inside the caller's scope are returned.

**On students seeing their own signal.** The endpoint is scoped, not
role-restricted, so a Student calling it receives risk signals on their own
evidence and nothing else — `test_student_anomalies_never_include_other_students`
pins that. The Angular route guard does not surface it in the student interface,
which is a UX choice; the data boundary is the scope, and a student reading a
signal about their own record is not a disclosure. It is worth knowing that this
means the signal is not hidden from the person it describes.

## 3. Engagement clustering — K-Means

| | |
|---|---|
| Module | `ml/engagement/kmeans.py`, orchestrated by `apps.ai.services.engagement` |
| Endpoint | `GET /api/v1/engagement/` |
| Scope | A student sees only their own label; staff see the distribution inside their scope; HOD/Admin also see per-student rows within scope. |
| Model version | `kmeans-engagement-v1` |

**Inputs** (eight per-student features): `registrations`, `participations`,
`verified`, `attendance_approved`, `od_approved`, `official_achievements`,
`category_diversity`, `recency_score` (a 0–1 score over a 180-day window).

**Output.** A `LOW` / `MODERATE` / `HIGH` label per student, plus the cluster
distribution.

**Why the labels are stable.** K-Means cluster ids are arbitrary — cluster 0 is
not "low" — and can flip between fits. So the label is never taken from the
cluster id. Each centroid is scored with a documented weighted formula in
original feature units (`ENGAGEMENT_WEIGHTS = [1, 3, 3, 2, 1, 3, 1, 2]`: a
verified participation is worth three registrations, an official achievement
three, and so on), the centroids are sorted by that score, and the labels are
assigned in that order.

**Small-data policy** (deterministic and documented): 0 or 1 student →
`INSUFFICIENT_DATA`; 2 students → K = 2, labelled LOW/HIGH; 3 or more → K = 3.
K is additionally capped at the number of *distinct* feature vectors, and if
that leaves K = 1 every student is labelled `MODERATE` and the response says
why.

> **An engagement label is a description of counts, not an academic judgment.**
> "LOW engagement" says this student's participation counts sit in the lowest
> cluster of the current population. It is not a grade, a ranking, or a
> statement about a student's worth.

## 4. Trend analysis — statistical, not a model

Period-over-period change, direction and moving average live in
`apps/analytics/trends.py` and are plain arithmetic. `ml/trend_analysis/` is a
deliberately empty package whose `__init__.py` documents that fact, so the `ml/`
layout matches the specification without creating a second, disagreeing
implementation.

## Training and inference

Models are **fitted on request** from live data — there is no training pipeline,
no model registry and no persisted artefact. For this dataset size the fit is
milliseconds and the result is always current; the response reports its own
`inference_ms`. The cost of that choice is bounded by a dedicated `ai` throttle
scope (30 requests/minute per user), because on-request fitting is one of the
two most expensive things an authenticated user can ask the server to do.

There is **no ground-truth validation dataset** for any of these models, and
none is claimed. The recommender's ranking, the forest's levels and the
clustering's labels are validated by *behavioural* tests — determinism, cold
start, small-data policy, scope isolation, failure containment — not by accuracy
metrics that would have nothing to be measured against.

## Failure behaviour summary

| Situation | Response |
|-----------|----------|
| Too little data | `200` with `available: false`, `reason: "INSUFFICIENT_DATA"`, empty `results` |
| No actionable events (recommendations) | `200` with `available: true`, `reason: "NO_ACTIONABLE_EVENTS"`, empty `results` |
| Any unexpected exception | `200` with `available: false`, `reason: "MODEL_ERROR"`; traceback logged server-side only |
| Caller out of scope for a named id | `404` at the view layer, before any model runs |
| Core workflow | Unaffected in every case above |
