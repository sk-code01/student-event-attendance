"""Reverse geocoding of a capture's coordinates (requirement 13).

The two properties that matter are that a capture is never lost to a geocoding
problem, and that the system never claims a precision it does not have.
"""

import json
import urllib.error
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.participation.geocoding import Precision, reverse_geocode


NOMINATIM_BUILDING = {
    'display_name': '12, Example Road, Bengaluru, Karnataka, 560001, India',
    'address': {'house_number': '12', 'road': 'Example Road'},
}
NOMINATIM_AREA = {
    'display_name': 'Example Road, Bengaluru, Karnataka, 560001, India',
    'address': {'road': 'Example Road'},
}
GOOGLE_ROOFTOP = {
    'status': 'OK',
    'results': [{
        'formatted_address': '12 Example Road, Bengaluru, Karnataka 560001, India',
        'geometry': {'location_type': 'ROOFTOP'},
    }],
}


class ProviderDisabledTests(SimpleTestCase):
    @override_settings(GEOCODING_PROVIDER='none')
    def test_the_default_provider_makes_no_request_and_resolves_nothing(self):
        with patch('apps.participation.geocoding._get_json') as get_json:
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=10))
        get_json.assert_not_called()

    @override_settings(GEOCODING_PROVIDER='something-unconfigured')
    def test_an_unknown_provider_resolves_nothing_rather_than_raising(self):
        self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=10))


@override_settings(GEOCODING_PROVIDER='nominatim')
class NominatimTests(SimpleTestCase):
    def test_a_building_level_result_is_exact(self):
        with patch('apps.participation.geocoding._get_json', return_value=NOMINATIM_BUILDING):
            resolved = reverse_geocode(12.97, 77.59, gps_accuracy=8)

        self.assertEqual(resolved.precision, Precision.EXACT)
        self.assertIn('Example Road', resolved.address)
        self.assertEqual(resolved.provider, 'nominatim')

    def test_a_street_level_result_is_only_approximate(self):
        with patch('apps.participation.geocoding._get_json', return_value=NOMINATIM_AREA):
            resolved = reverse_geocode(12.97, 77.59, gps_accuracy=8)

        self.assertEqual(resolved.precision, Precision.APPROXIMATE)

    def test_poor_gps_accuracy_downgrades_an_exact_result(self):
        # The provider would happily name a building, but a 300 m accuracy
        # circle covers many of them — naming one would overstate the evidence.
        with patch('apps.participation.geocoding._get_json', return_value=NOMINATIM_BUILDING):
            resolved = reverse_geocode(12.97, 77.59, gps_accuracy=300)

        self.assertEqual(resolved.precision, Precision.APPROXIMATE)
        self.assertIn('Example Road', resolved.address)

    def test_an_empty_display_name_resolves_nothing(self):
        with patch('apps.participation.geocoding._get_json', return_value={'display_name': '  '}):
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))


@override_settings(GEOCODING_PROVIDER='google', GEOCODING_API_KEY='test-key')
class GoogleTests(SimpleTestCase):
    def test_a_rooftop_result_is_exact(self):
        with patch('apps.participation.geocoding._get_json', return_value=GOOGLE_ROOFTOP):
            resolved = reverse_geocode(12.97, 77.59, gps_accuracy=8)

        self.assertEqual(resolved.precision, Precision.EXACT)
        self.assertEqual(resolved.provider, 'google')

    def test_a_non_ok_status_resolves_nothing(self):
        with patch('apps.participation.geocoding._get_json', return_value={'status': 'ZERO_RESULTS'}):
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))

    @override_settings(GEOCODING_API_KEY='')
    def test_a_missing_api_key_resolves_nothing_rather_than_calling_out(self):
        with patch('apps.participation.geocoding._get_json') as get_json:
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))
        get_json.assert_not_called()


@override_settings(GEOCODING_PROVIDER='nominatim')
class FailureIsAlwaysSurvivableTests(SimpleTestCase):
    """A capture must never be lost because a third-party lookup failed."""

    def test_a_network_error_resolves_nothing(self):
        with patch('apps.participation.geocoding._get_json', side_effect=urllib.error.URLError('down')):
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))

    def test_a_timeout_resolves_nothing(self):
        with patch('apps.participation.geocoding._get_json', side_effect=TimeoutError()):
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))

    def test_malformed_json_resolves_nothing(self):
        with patch(
            'apps.participation.geocoding._get_json',
            side_effect=json.JSONDecodeError('bad', 'doc', 0),
        ):
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))

    def test_an_unexpected_provider_error_resolves_nothing(self):
        # Deliberately not an anticipated exception type: the capture still has
        # to survive it.
        with patch('apps.participation.geocoding._get_json', side_effect=RuntimeError('surprise')):
            self.assertIsNone(reverse_geocode(12.97, 77.59, gps_accuracy=8))
