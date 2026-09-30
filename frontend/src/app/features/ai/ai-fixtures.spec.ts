import {
  AnomaliesResponse,
  EngagementResponse,
  RecommendationsResponse,
  RiskSignal,
} from '../../core/models/ai.model';

/** Shared deterministic payloads for the AI component specs. */

export const DISCLAIMER =
  'AI-generated decision-support signal. Final academic decisions remain with authorized Faculty/Event Coordinator personnel.';

const ENVELOPE = { generated_at: '2026-09-15T10:00:00Z', disclaimer: DISCLAIMER, inference_ms: 12.5 };

export function recommendations(overrides: Partial<RecommendationsResponse> = {}): RecommendationsResponse {
  return {
    ...ENVELOPE,
    available: true,
    model: 'knn',
    model_version: 'knn-similarity-v1',
    feature_version: 'features-v1',
    score_basis: 'KNN similarity in (0, 1]. Not a probability.',
    history_size: 3,
    candidate_count: 2,
    results: [
      {
        event_id: 11, score: 0.91,
        reasons: ['Matches a category you have engaged with before (Technical).', 'Organised by your department.'],
        event: {
          id: 11, title: 'CS Tech Open', category: 'Technical', event_date: '2026-09-25',
          venue: 'Main Auditorium', registration_end_date: '2026-09-20', department: 'Computer Science',
        },
      },
      {
        event_id: 12, score: 0.42, reasons: [],
        event: {
          id: 12, title: 'CS Sports Open', category: 'Sports', event_date: '2026-10-05',
          venue: 'Ground', registration_end_date: '2026-09-20', department: 'Computer Science',
        },
      },
    ],
    ...overrides,
  };
}

export function coldStart(): RecommendationsResponse {
  return recommendations({
    model: 'cold_start', model_version: 'cold-start-v1', history_size: 0,
    score_basis: 'Deterministic cold-start ranking. Not a model output and not a probability.',
    results: [{
      event_id: 11, score: 0.8, reasons: ['Organised by your department.'],
      event: {
        id: 11, title: 'CS Tech Open', category: 'Technical', event_date: '2026-09-25',
        venue: 'Main Auditorium', registration_end_date: '2026-09-20', department: 'Computer Science',
      },
    }],
  });
}

export function unavailable<T extends { available: boolean }>(
  model: string, reason: string, extra: Partial<T> = {},
): T {
  return { ...ENVELOPE, available: false, model, reason, results: [], ...extra } as unknown as T;
}

export function riskSignal(overrides: Partial<RiskSignal> = {}): RiskSignal {
  return {
    evidence_id: 7, participation_id: 70, student: 'studentmid', event_id: 3, event_title: 'CS Cultural Past',
    effective_decision: 'SUBMITTED', risk_level: 'HIGH', anomaly_score: 0.6123,
    signals: ['Capture taken 5000 m from the venue (typical: 20 m).', 'Evidence resubmitted 1 time.'],
    features: { capture_count: 2, version_count: 2, max_venue_distance_m: 5000 },
    ...overrides,
  };
}

export function anomalies(overrides: Partial<AnomaliesResponse> = {}): AnomaliesResponse {
  return {
    ...ENVELOPE,
    available: true,
    model: 'isolation_forest',
    model_version: 'isolation-forest-v1',
    feature_version: 'features-v1',
    score_basis: 'Negated Isolation Forest score_samples. Not a probability.',
    thresholds: { high: 0.55, medium: 0.5, rule: 'HIGH = outlier AND >= 90th percentile; MEDIUM = either; otherwise LOW.' },
    population: { n_samples: 6, n_features: 9 },
    feature_definitions: [
      { name: 'capture_count', temporal_status: 'PRE-VERIFICATION' },
      { name: 'prior_rejection_ratio', temporal_status: 'HISTORICAL' },
    ],
    summary: { HIGH: 1, MEDIUM: 1, LOW: 1 },
    results: [
      riskSignal(),
      riskSignal({ evidence_id: 8, student: 'studenthigh', risk_level: 'MEDIUM', anomaly_score: 0.51, signals: [] }),
      riskSignal({ evidence_id: 9, student: 'studentec', risk_level: 'LOW', anomaly_score: 0.40, signals: [],
        effective_decision: 'VERIFIED' }),
    ],
    ...overrides,
  };
}

export function engagementStaff(overrides: Partial<EngagementResponse> = {}): EngagementResponse {
  return {
    ...ENVELOPE,
    available: true,
    model: 'kmeans',
    model_version: 'kmeans-engagement-v1',
    feature_version: 'features-v1',
    k: 3,
    label_order: ['LOW', 'MODERATE', 'HIGH'],
    population: { n_samples: 5, n_features: 8 },
    centroids: [
      { label: 'LOW', engagement_score: 0.2, features: { registrations: 0.5 } },
      { label: 'MODERATE', engagement_score: 6.5, features: { registrations: 1 } },
      { label: 'HIGH', engagement_score: 25.0, features: { registrations: 4 } },
    ],
    engagement_formula: { description: 'Weighted sum of centroid features.', weights: { registrations: 1, participations: 3 } },
    note: '',
    distribution: { LOW: 2, MODERATE: 1, HIGH: 1 },
    scoped_students: 4,
    results: [
      { student_id: 1, student: 'studentcold', label: 'LOW', features: { registrations: 0, participations: 0 } },
      { student_id: 2, student: 'studenthigh', label: 'HIGH', features: { registrations: 4, participations: 3 } },
    ],
    ...overrides,
  };
}

export function engagementStudent(): EngagementResponse {
  const base = engagementStaff();
  delete base.distribution;
  delete base.scoped_students;
  return {
    ...base,
    own: {
      label: 'MODERATE',
      features: { registrations: 1, participations: 1 },
      explanation: 'Based on your participation history — 1 registration, 1 participation — your activity pattern groups with students in the MODERATE engagement cluster. This describes a pattern of counts, not an academic judgment.',
    },
    results: [],
  };
}
