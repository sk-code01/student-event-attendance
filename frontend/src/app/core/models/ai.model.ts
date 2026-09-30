/**
 * AI decision-support payloads (Phase 8).
 *
 * Every response shares the `AiResponse` envelope. `available: false` is a
 * normal, expected answer — the model had too little data or failed — and
 * carries a `reason` code. Nothing here is a decision: the backend documents
 * each score as a similarity / isolation signal, never a probability or a
 * verdict, and the frontend renders it as exactly that.
 */

export type AiReason = 'INSUFFICIENT_DATA' | 'MODEL_ERROR' | 'NO_ACTIONABLE_EVENTS' | string;

export interface AiResponse {
  available: boolean;
  model: string;
  model_version?: string;
  feature_version?: string;
  reason?: AiReason;
  detail?: string;
  generated_at: string;
  disclaimer: string;
  inference_ms: number;
}

// --- Recommendations ------------------------------------------------------

export interface RecommendedEvent {
  id: number;
  title: string;
  category: string;
  event_date: string;
  venue: string;
  registration_end_date: string;
  department: string | null;
}

export interface Recommendation {
  event_id: number;
  /** Similarity or cold-start ranking score in (0, 1]. Not a probability. */
  score: number;
  reasons: string[];
  event: RecommendedEvent;
}

export interface RecommendationsResponse extends AiResponse {
  model: 'knn' | 'cold_start' | string;
  score_basis?: string;
  history_size?: number;
  candidate_count?: number;
  results: Recommendation[];
}

// --- Anomaly / risk signals ---------------------------------------------

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export interface RiskSignal {
  evidence_id: number;
  participation_id: number | null;
  student: string | null;
  event_id: number | null;
  event_title: string | null;
  effective_decision: string | null;
  risk_level: RiskLevel;
  /** Higher = more isolated from the population. Not a probability. */
  anomaly_score: number;
  signals: string[];
  features: Record<string, number | null>;
}

export interface AnomalyThresholds {
  high: number;
  medium: number;
  rule: string;
}

export interface FeatureDefinition {
  name: string;
  temporal_status: string;
}

export interface AnomaliesResponse extends AiResponse {
  score_basis?: string;
  thresholds?: AnomalyThresholds;
  population?: { n_samples: number; n_features: number };
  feature_definitions?: FeatureDefinition[];
  summary?: Record<RiskLevel, number> | Record<string, number>;
  results: RiskSignal[];
}

export interface AnomalyFilters {
  evidence?: number;
  limit?: number;
}

// --- Engagement -----------------------------------------------------------

export type EngagementLabel = 'LOW' | 'MODERATE' | 'HIGH';

export interface Centroid {
  label: EngagementLabel;
  engagement_score: number;
  features: Record<string, number>;
}

export interface OwnEngagement {
  label: EngagementLabel;
  features: Record<string, number>;
  explanation: string;
}

export interface StudentEngagement {
  student_id: number;
  student: string | null;
  label: EngagementLabel;
  features: Record<string, number>;
}

export interface EngagementResponse extends AiResponse {
  k?: number;
  label_order?: EngagementLabel[];
  population?: { n_samples: number; n_features: number };
  centroids?: Centroid[];
  engagement_formula?: { description: string; weights: Record<string, number> };
  note?: string;
  /** Students only. */
  own?: OwnEngagement | null;
  /** Staff only: counts per label inside the caller's scope. */
  distribution?: Record<string, number>;
  scoped_students?: number;
  /** Event Coordinator and Admin only; empty for Faculty and Students. */
  results: StudentEngagement[];
}
