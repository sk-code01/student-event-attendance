"""
Reverse geocoding for a live capture's coordinates.

Requirement 13 asks that reviewers see where a capture was taken rather than a
pair of raw numbers, while the underlying coordinates are still retained for
verification. Three rules shape everything here:

**It never blocks a capture.** The photo, the timestamp and the coordinates are
the evidence; an address is an aid to reading them. A geocoding provider that
is slow, rate-limited, misconfigured or down must not stop a student from
submitting on the one day they are allowed to. Every failure path returns None
and the capture proceeds.

**It never claims more precision than it has.** A street address is only
reported as EXACT when the provider says it resolved to a specific building
*and* the device's own GPS accuracy was good enough for that to be meaningful.
A 300-metre accuracy circle covers many buildings, so naming one of them would
be a fabrication dressed up as evidence.

**It is off by default.** The default provider makes no outbound request at
all, which is what a developer machine and the test suite need. An institution
that wants addresses configures a provider explicitly.

No new dependency: the standard library's urllib is enough for one GET, and
`requests` is not a pinned dependency of this project.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


class Precision:
    """How much the resolved address can be relied upon."""

    EXACT = 'EXACT'
    APPROXIMATE = 'APPROXIMATE'
    UNRESOLVED = 'UNRESOLVED'

    CHOICES = [
        (EXACT, 'Exact'),
        (APPROXIMATE, 'Approximate'),
        (UNRESOLVED, 'Unresolved'),
    ]


@dataclass(frozen=True)
class ResolvedAddress:
    address: str
    precision: str
    provider: str


def _get_json(url: str, *, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    timeout = getattr(settings, 'GEOCODING_TIMEOUT_SECONDS', 3)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            return None
        return json.loads(response.read().decode('utf-8'))


def _nominatim(latitude, longitude):
    """OpenStreetMap's reverse geocoder. Needs no API key, but its usage policy
    requires an identifying User-Agent, so one is always sent."""
    query = urllib.parse.urlencode({
        'lat': f'{latitude}', 'lon': f'{longitude}', 'format': 'jsonv2', 'zoom': 18,
    })
    payload = _get_json(
        f'https://nominatim.openstreetmap.org/reverse?{query}',
        headers={'User-Agent': getattr(settings, 'GEOCODING_USER_AGENT', 'SEAMS-AI')},
    )
    if not payload:
        return None

    address = (payload.get('display_name') or '').strip()
    if not address:
        return None

    # A house number means the provider placed this at a specific building
    # rather than somewhere along a street or inside an area.
    has_house_number = bool((payload.get('address') or {}).get('house_number'))
    precision = Precision.EXACT if has_house_number else Precision.APPROXIMATE
    return ResolvedAddress(address=address, precision=precision, provider='nominatim')


def _google(latitude, longitude):
    api_key = getattr(settings, 'GEOCODING_API_KEY', '')
    if not api_key:
        logger.warning('Geocoding provider is "google" but GEOCODING_API_KEY is not set.')
        return None

    query = urllib.parse.urlencode({'latlng': f'{latitude},{longitude}', 'key': api_key})
    payload = _get_json(f'https://maps.googleapis.com/maps/api/geocode/json?{query}')
    if not payload or payload.get('status') != 'OK':
        return None

    results = payload.get('results') or []
    if not results:
        return None

    best = results[0]
    address = (best.get('formatted_address') or '').strip()
    if not address:
        return None

    location_type = ((best.get('geometry') or {}).get('location_type') or '').upper()
    precision = Precision.EXACT if location_type == 'ROOFTOP' else Precision.APPROXIMATE
    return ResolvedAddress(address=address, precision=precision, provider='google')


_PROVIDERS = {
    'nominatim': _nominatim,
    'google': _google,
}

# Beyond this, the coordinates themselves are too uncertain for a building-level
# address to mean anything, whatever the provider reports.
_EXACT_ACCURACY_CEILING_METERS = 50


def reverse_geocode(latitude, longitude, *, gps_accuracy=None):
    """Best-effort address for a capture, or None.

    `gps_accuracy` is the device's own reported accuracy in metres. It is taken
    into account deliberately: a provider will happily name a building for a
    coordinate that the phone only knew to within 300 metres, and repeating
    that as an exact address would overstate the evidence.
    """
    provider_name = getattr(settings, 'GEOCODING_PROVIDER', 'none')
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        return None

    try:
        resolved = provider(latitude, longitude)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        # Never propagates: a capture must not fail because a third-party
        # lookup did. Logged so a misconfiguration is still visible.
        logger.warning('Reverse geocoding failed via %s: %s', provider_name, exc)
        return None
    except Exception:  # noqa: BLE001 - deliberately broad; see the note above
        logger.exception('Unexpected reverse geocoding failure via %s', provider_name)
        return None

    if resolved is None:
        return None

    if (
        resolved.precision == Precision.EXACT
        and gps_accuracy is not None
        and gps_accuracy > _EXACT_ACCURACY_CEILING_METERS
    ):
        return ResolvedAddress(
            address=resolved.address,
            precision=Precision.APPROXIMATE,
            provider=resolved.provider,
        )
    return resolved
