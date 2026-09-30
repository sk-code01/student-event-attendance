"""
Pure-model unit tests over hand-written arrays. No Django, no database — this
is where determinism, ordering and small-data behaviour are pinned down
exactly, independent of any fixture.
"""

import numpy as np
from django.test import SimpleTestCase

from ml.anomaly_detection import isolation_forest as forest
from ml.engagement import kmeans
from ml.recommendation import knn


class KnnUnitTests(SimpleTestCase):
    def test_identical_candidate_scores_one_and_distant_candidate_scores_less(self):
        history = np.array([[1.0, 0.0, 0.0]])
        candidates = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        scores = knn.score_candidates(history=history, candidates=candidates)
        self.assertAlmostEqual(scores[0], 1.0)
        self.assertLess(scores[1], scores[0])
        self.assertTrue(np.all(scores > 0) and np.all(scores <= 1))

    def test_ranking_is_deterministic(self):
        rng = np.random.default_rng(0)
        history, candidates = rng.random((6, 4)), rng.random((5, 4))
        first = knn.score_candidates(history=history, candidates=candidates)
        second = knn.score_candidates(history=history, candidates=candidates)
        np.testing.assert_array_equal(first, second)

    def test_k_is_capped_at_history_size(self):
        scores = knn.score_candidates(history=np.ones((2, 3)), candidates=np.ones((1, 3)), k=50)
        self.assertEqual(scores.shape, (1,))
        self.assertAlmostEqual(scores[0], 1.0)

    def test_empty_history_is_refused_so_cold_start_is_an_explicit_choice(self):
        with self.assertRaises(ValueError):
            knn.score_candidates(history=np.zeros((0, 3)), candidates=np.ones((1, 3)))

    def test_no_candidates_returns_an_empty_score_array(self):
        scores = knn.score_candidates(history=np.ones((1, 3)), candidates=np.zeros((0, 3)))
        self.assertEqual(scores.shape, (0,))

    def test_feature_width_mismatch_is_an_error_not_a_silent_misrank(self):
        with self.assertRaises(ValueError):
            knn.score_candidates(history=np.ones((1, 3)), candidates=np.ones((1, 4)))


class IsolationForestUnitTests(SimpleTestCase):
    def _population(self):
        rng = np.random.default_rng(1)
        normal = rng.normal(loc=[20, 10, 5], scale=[2, 1, 1], size=(19, 3))
        unusual = np.array([[5000.0, 500.0, 7200.0]])
        return np.vstack([normal, unusual])

    def test_the_planted_outlier_gets_the_highest_score_and_is_flagged(self):
        result = forest.fit_and_score(self._population())
        self.assertEqual(int(np.argmax(result.anomaly_scores)), 19)
        self.assertTrue(result.is_outlier[19])
        self.assertEqual(result.levels[19], forest.RiskLevel.HIGH)

    def test_normal_rows_are_mostly_low(self):
        result = forest.fit_and_score(self._population())
        low = sum(1 for level in result.levels[:19] if level == forest.RiskLevel.LOW)
        self.assertGreaterEqual(low, 13)

    def test_scores_are_deterministic_for_a_fixed_random_state(self):
        a = forest.fit_and_score(self._population(), random_state=42)
        b = forest.fit_and_score(self._population(), random_state=42)
        np.testing.assert_array_equal(a.anomaly_scores, b.anomaly_scores)
        self.assertEqual(a.levels, b.levels)

    def test_thresholds_are_population_percentiles_and_reported(self):
        result = forest.fit_and_score(self._population())
        self.assertAlmostEqual(result.high_threshold, float(np.percentile(result.anomaly_scores, 90)))
        self.assertAlmostEqual(result.medium_threshold, float(np.percentile(result.anomaly_scores, 75)))
        self.assertGreaterEqual(result.high_threshold, result.medium_threshold)

    def test_too_few_samples_is_insufficient_data_not_a_fit(self):
        with self.assertRaises(forest.InsufficientData):
            forest.fit_and_score(np.ones((forest.MIN_SAMPLES - 1, 3)))

    def test_nan_features_are_imputed_rather_than_poisoning_the_forest(self):
        population = self._population()
        population[3, 1] = np.nan
        result = forest.fit_and_score(population)
        self.assertFalse(np.isnan(result.anomaly_scores).any())


class KMeansUnitTests(SimpleTestCase):
    WEIGHTS = np.array([1.0, 3.0])

    def test_labels_follow_centroid_engagement_order_not_cluster_ids(self):
        # Three well-separated groups; whichever ids sklearn assigns, the
        # highest-engagement group must be labelled HIGH.
        features = np.array([
            [0, 0], [0, 0], [1, 0],           # low
            [5, 3], [5, 3], [6, 3],           # moderate
            [20, 10], [20, 10], [21, 11],     # high
        ], dtype=float)
        result = kmeans.cluster_students(features, weights=self.WEIGHTS)
        self.assertEqual(result.k, 3)
        self.assertEqual(result.labels[:3], ['LOW'] * 3)
        self.assertEqual(result.labels[3:6], ['MODERATE'] * 3)
        self.assertEqual(result.labels[6:], ['HIGH'] * 3)
        self.assertEqual(result.label_order, ['LOW', 'MODERATE', 'HIGH'])
        self.assertEqual(result.centroid_scores, sorted(result.centroid_scores))

    def test_clustering_is_deterministic(self):
        rng = np.random.default_rng(2)
        features = rng.random((12, 2)) * 10
        a = kmeans.cluster_students(features, weights=self.WEIGHTS)
        b = kmeans.cluster_students(features, weights=self.WEIGHTS)
        self.assertEqual(a.labels, b.labels)

    def test_two_students_form_low_and_high(self):
        result = kmeans.cluster_students(np.array([[0, 0], [10, 5]], dtype=float), weights=self.WEIGHTS)
        self.assertEqual(result.k, 2)
        self.assertEqual(result.labels, ['LOW', 'HIGH'])

    def test_one_student_is_insufficient_data(self):
        with self.assertRaises(kmeans.InsufficientData):
            kmeans.cluster_students(np.array([[3, 1]], dtype=float), weights=self.WEIGHTS)

    def test_zero_students_is_insufficient_data(self):
        with self.assertRaises(kmeans.InsufficientData):
            kmeans.cluster_students(np.zeros((0, 2)), weights=self.WEIGHTS)

    def test_identical_students_form_one_moderate_group_with_a_note(self):
        result = kmeans.cluster_students(np.array([[2, 1]] * 5, dtype=float), weights=self.WEIGHTS)
        self.assertEqual(result.k, 1)
        self.assertEqual(set(result.labels), {'MODERATE'})
        self.assertIn('identical', result.note)

    def test_k_is_capped_at_distinct_vectors(self):
        # Five rows but only two distinct points: K must drop to 2.
        features = np.array([[0, 0], [0, 0], [0, 0], [9, 9], [9, 9]], dtype=float)
        result = kmeans.cluster_students(features, weights=self.WEIGHTS)
        self.assertEqual(result.k, 2)
        self.assertEqual(result.labels, ['LOW', 'LOW', 'LOW', 'HIGH', 'HIGH'])
